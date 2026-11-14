"""Il magazzino degli esiti a piu' orizzonti, col controllo abbinato.

Maturazione (`matura`, a fine scansione e dallo script di riempimento) e
lettura per il cubo delle prestazioni (`celle_per_detector`). Il perche' della
tabella e dei suoi due riferimenti sta in `app.models.esito_orizzonte`.

⚠️ Tre regole che non sono dettagli.

1. **L'aritmetica del riferimento di mercato e' quella del magazzino
   esistente** (`signal_outcome_service._universe_fwd_medians`, solo societa'):
   all'orizzonte proprio le due tabelle devono dire la stessa cosa sugli alert
   mai rivisti, e lo script di riempimento lo verifica.

2. **Il controllo si confronta con la MEDIANA dei cinque, non con la media.**
   Con la mediana il colpo vale 3/6 = 50% sotto ipotesi nulla per qualunque
   distribuzione; con la media no, perche' i rendimenti sono asimmetrici a
   destra — la stessa ragione per cui il riferimento dell'universo e' la
   mediana (CLAUDE.md, invariante #3). Un test lo fissa su dati asimmetrici,
   con il controllo negativo sulla media.

3. **Il verdetto si da' solo all'orizzonte PROPRIO del detector.** Quattro
   orizzonti sono quattro confronti: leggere il migliore dei quattro come
   risultato e' la moltiplicazione dei test che lo studio condizionale ha gia'
   pagato (regola B). Gli altri orizzonti DESCRIVONO, e lo dicono.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, EsitoOrizzonte, Stock
from app.services.signal_drift_service import _horizon_days
from app.services.signal_outcome_service import (
    _load_universe_closes,
    _trigger_index,
    _universe_fwd_medians,
)
from app.stats.sizing import independent_blocks, sized_interval, tasso_per_giorno

#: In sedute. 1 per la lettura piu' fine; gli altri sono gli orizzonti dei
#: detector, cosi' ognuno ha anche la riga del proprio.
ORIZZONTI: tuple[int, ...] = (1, 5, 21, 63)

#: Cambia quando cambia una regola di questo modulo.
METODO = "1"

#: Quanti titoli di controllo per esito. Cinque perche' con la mediana di un
#: numero DISPARI l'ipotesi nulla vale 50% esatti (vedi il modulo).
CONTROLLI = 5

#: Un titolo con un alert dello STESSO detector entro questi giorni non fa da
#: controllo: misurerebbe il segnale contro se stesso.
ESCLUSIONE_GIORNI = 5

#: Sedute della volatilita' che definisce la fascia: la stessa finestra di
#: `vol20` in `app.signals.contesto_emissione`.
VOL_SEDUTE = 20

#: Sotto questo numero di titoli quel giorno le fasce non si calcolano: tre
#: terzili su venti titoli sono rumore.
MIN_SEZIONE = 30

#: Oltre questa eta' un alert non si cerca piu': se in 200 giorni di calendario
#: non ha maturato l'orizzonte piu' lungo (63 sedute, ~90 giorni) la sua serie
#: e' ferma, e ricaricarla a ogni scansione allargherebbe la finestra per
#: sempre. Il riempimento la spegne.
ETA_MASSIMA_GIORNI = 200


def _snapshot(alert: Alert) -> dict:
    try:
        snap = json.loads(alert.snapshot) if alert.snapshot else {}
    except (ValueError, TypeError):
        return {}
    return snap if isinstance(snap, dict) else {}


def ancora(alert: Alert) -> date | None:
    """Il giorno in cui l'alert e' comparso; `signal_date` se e' piu' vecchio
    del campo (ripiego dichiarato)."""
    grezzo = _snapshot(alert).get("first_emitted_at")
    if isinstance(grezzo, str) and len(grezzo) >= 10:
        try:
            return date.fromisoformat(grezzo[:10])
        except ValueError:
            pass
    return alert.signal_date


def _tono(alert: Alert) -> str | None:
    t = _snapshot(alert).get("tone")
    return t if t in ("bull", "bear") else None


def volatilita(closes: np.ndarray) -> np.ndarray:
    """Deviazione standard dei rendimenti delle ultime `VOL_SEDUTE` sedute,
    allineata alle barre (NaN dove la storia non basta)."""
    out = np.full(len(closes), np.nan)
    if len(closes) <= VOL_SEDUTE:
        return out
    rend = pd.Series(closes[1:] / closes[:-1] - 1.0)
    out[1:] = rend.rolling(VOL_SEDUTE).std().to_numpy()
    return out


def fascia(v: float, tagli: tuple[float, float]) -> int:
    """0, 1 o 2: il terzile di volatilita' di quel giorno."""
    return 0 if v <= tagli[0] else 1 if v <= tagli[1] else 2


def ordine_dei_controlli(candidati: list[int], seme: int) -> list[int]:
    """I candidati in un ordine casuale RIPRODUCIBILE: stesso alert, stessi
    controlli, a ogni maturazione e a ogni riempimento."""
    ordinati = sorted(candidati)
    random.Random(seme).shuffle(ordinati)
    return ordinati


def contro_il_controllo(
    rendimento: float, controlli: list[float], tono: str,
) -> tuple[float, float, int]:
    """(mediana dei controlli, eccesso col segno del tono, colpo 1/0)."""
    mediana = float(np.median(controlli))
    eccesso = rendimento - mediana
    if tono == "bear":
        eccesso = -eccesso
    return mediana, eccesso, 1 if eccesso > 0 else 0


@dataclass
class _Serie:
    date: np.ndarray
    chiusure: np.ndarray
    vol: np.ndarray


def _da_esaminare(db: Session, oggi: date, eta_massima: int | None) -> list[Alert]:
    """Gli alert a cui manca almeno un orizzonte."""
    fatti = (
        select(EsitoOrizzonte.alert_id, func.count().label("n"))
        .group_by(EsitoOrizzonte.alert_id)
        .subquery()
    )
    cond = [
        Alert.signal_name.is_not(None),
        Alert.signal_date.is_not(None),
        func.coalesce(fatti.c.n, 0) < len(ORIZZONTI),
    ]
    # `signal_date` e' sempre >= dell'ancora (la revisione la sposta solo in
    # avanti), quindi come prefiltro non perde nessuno.
    if eta_massima is not None:
        cond.append(Alert.signal_date >= oggi - timedelta(days=eta_massima))
    return list(db.execute(
        select(Alert).outerjoin(fatti, fatti.c.alert_id == Alert.id).where(*cond)
    ).scalars())


def _esclusioni(
    db: Session, dal: date,
) -> dict[tuple[str, int], list[tuple[date, date]]]:
    """{(detector, titolo): intervalli in cui quel titolo aveva un alert del
    detector}, allargati di `ESCLUSIONE_GIORNI` per lato."""
    out: dict[tuple[str, int], list[tuple[date, date]]] = defaultdict(list)
    righe = db.execute(
        select(Alert).where(
            Alert.signal_name.is_not(None),
            Alert.signal_date.is_not(None),
            Alert.signal_date >= dal - timedelta(days=2 * ESCLUSIONE_GIORNI),
        )
    ).scalars()
    margine = timedelta(days=ESCLUSIONE_GIORNI)
    for a in righe:
        inizio = ancora(a) or a.signal_date
        out[(a.signal_name, a.stock_id)].append((inizio - margine, a.signal_date + margine))
    return out


def _escluso(intervalli: list[tuple[date, date]], giorno: date) -> bool:
    return any(da <= giorno <= a for da, a in intervalli)


class _Calcolo:
    """Lo stato condiviso del calcolo, costruito una volta: serie dal giorno
    `dal`, mediane dell'universo, sezioni di volatilita' per giorno ed
    esclusioni. Serve sia alla maturazione sia al riallineamento, cosi' le due
    strade non possono calcolare in modo diverso."""

    def __init__(self, db: Session, dal: date) -> None:
        # Margine per la volatilita' (20 sedute) prima della prima ancora.
        grezze = _load_universe_closes(db, since=dal - timedelta(days=45))
        etf = set(db.execute(select(Stock.id).where(Stock.instrument_type == "etf")).scalars())
        self.serie = {sid: _Serie(ds, cs, volatilita(cs)) for sid, (ds, cs) in grezze.items()}
        societa = {sid: v for sid, v in grezze.items() if sid not in etf}
        self.mediane = {h: _universe_fwd_medians(societa, h) for h in ORIZZONTI}
        # La sezione trasversale di ogni giorno: (titolo, volatilita', indice).
        self.sezione: dict[date, list[tuple[int, float, int]]] = defaultdict(list)
        for sid, s in self.serie.items():
            if sid in etf:
                continue
            for i, v in enumerate(s.vol):
                if v == v:
                    self.sezione[s.date[i]].append((sid, float(v), i))
        self._tagli: dict[date, tuple[float, float] | None] = {}
        self.esclusi = _esclusioni(db, dal)

    def tagli(self, g: date) -> tuple[float, float] | None:
        if g not in self._tagli:
            vols = [v for _, v, _ in self.sezione.get(g, ())]
            self._tagli[g] = (
                (float(np.quantile(vols, 1 / 3)), float(np.quantile(vols, 2 / 3)))
                if len(vols) >= MIN_SEZIONE else None
            )
        return self._tagli[g]

    def esiti(self, a: Alert, tono: str, anc: date, orizzonti: list[int]) -> dict[int, dict]:
        """{orizzonte: valori} per gli orizzonti gia' trascorsi."""
        s = self.serie.get(a.stock_id)
        if not orizzonti or s is None:
            return {}
        ti = _trigger_index(s.date, anc)
        if ti is None:
            return {}
        ingresso = float(s.chiusure[ti])
        if ingresso <= 0:
            return {}
        giorno = s.date[ti]

        ordine: list[tuple[int, int]] = []
        t = self.tagli(giorno)
        mia_vol = s.vol[ti]
        if t is not None and mia_vol == mia_vol:
            mia = fascia(float(mia_vol), t)
            candidati = {
                sid: i for sid, v, i in self.sezione[giorno]
                if sid != a.stock_id and fascia(v, t) == mia
                and not _escluso(self.esclusi.get((a.signal_name, sid), []), giorno)
            }
            ordine = [(sid, candidati[sid]) for sid in ordine_dei_controlli(list(candidati), a.id)]

        out: dict[int, dict] = {}
        for h in orizzonti:
            if ti + h >= len(s.chiusure):
                continue  # orizzonte non ancora trascorso
            uscita = float(s.chiusure[ti + h])
            rend = uscita / ingresso - 1.0
            med = self.mediane[h].get(giorno)
            ecc_m = colpo_m = None
            if med is not None:
                ecc_m = (rend - med) if tono == "bull" else -(rend - med)
                colpo_m = 1 if ecc_m > 0 else 0

            rend_controlli: list[float] = []
            for sid, i in ordine:
                cs = self.serie[sid].chiusure
                if i + h < len(cs) and cs[i] > 0:
                    rend_controlli.append(float(cs[i + h] / cs[i] - 1.0))
                    if len(rend_controlli) == CONTROLLI:
                        break
            ctrl = ecc_c = colpo_c = n_ctrl = None
            if len(rend_controlli) == CONTROLLI:
                ctrl, ecc_c, colpo_c = contro_il_controllo(rend, rend_controlli, tono)
                n_ctrl = CONTROLLI
            out[h] = {
                "ancora": giorno, "ingresso": ingresso, "uscita": uscita, "rendimento": rend,
                "mediana_universo": med, "eccesso_mediana": ecc_m, "colpo_mediana": colpo_m,
                "controllo": ctrl, "controlli_n": n_ctrl, "eccesso_controllo": ecc_c,
                "colpo_controllo": colpo_c,
            }
        return out


def matura(
    db: Session, *, commit: bool = True, eta_massima_giorni: int | None = ETA_MASSIMA_GIORNI,
    oggi: date | None = None,
) -> int:
    """Scrive gli orizzonti maturati che mancano. Rende quante righe.

    Idempotente: una coppia (alert, orizzonte) gia' scritta non si ricalcola
    qui (la riallinea `riallinea`). `eta_massima_giorni=None` esamina tutta la
    storia (riempimento)."""
    oggi = oggi or datetime.now(UTC).date()
    alert = []
    for a in _da_esaminare(db, oggi, eta_massima_giorni):
        t, anc = _tono(a), ancora(a)
        if t is not None and anc is not None:
            alert.append((a, t, anc))
    if not alert:
        logger.info("[esiti-orizzonti] nessun alert da esaminare")
        return 0

    ids = {a.id for a, _, _ in alert}
    gia: dict[int, set[int]] = defaultdict(set)
    for aid, h in db.execute(select(EsitoOrizzonte.alert_id, EsitoOrizzonte.orizzonte)):
        if aid in ids:
            gia[aid].add(h)

    calcolo = _Calcolo(db, min(anc for _, _, anc in alert))
    adesso = datetime.now(UTC)
    scritte = 0
    for a, tono, anc in alert:
        mancano = [h for h in ORIZZONTI if h not in gia[a.id]]
        for h, v in calcolo.esiti(a, tono, anc, mancano).items():
            db.add(EsitoOrizzonte(
                alert_id=a.id, stock_id=a.stock_id, detector=a.signal_name, tono=tono,
                orizzonte=h, metodo=METODO, maturato_il=adesso, **v,
            ))
            scritte += 1

    if commit and scritte:
        db.commit()
    logger.info(f"[esiti-orizzonti] {scritte} righe scritte su {len(alert)} alert esaminati")
    return scritte


def _diverso(a: object, b: object) -> bool:
    if a is None or b is None:
        return (a is None) != (b is None)
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) > 1e-12
    return a != b


def riallinea(db: Session, *, commit: bool = True) -> tuple[int, int]:
    """Ricalcola dai dati di OGGI ogni riga gia' scritta e aggiorna quelle
    cambiate. Rende (esaminate, cambiate).

    ⚠️ Perche' (FA-164). Le barre salvate vengono riscritte dopo la
    maturazione — riscaricamento dell'ultimo mese, riparazione dei buchi,
    aggiustamenti per split — e un esito fissato una volta fotografa uno stato
    dei dati poi corretto. Misurato il 2026-11-14 su `signal_outcomes`: il 90%
    delle mediane non si riproduceva piu', e il 2,6% dei colpi cambiava segno.
    Si aggiornano solo le righe cambiate, per non riscrivere il magazzino
    intero a ogni passata."""
    righe = list(db.execute(select(EsitoOrizzonte)).scalars())
    if not righe:
        return 0, 0
    per_alert: dict[int, list[EsitoOrizzonte]] = defaultdict(list)
    for r in righe:
        per_alert[r.alert_id].append(r)
    alert = {a.id: a for a in db.execute(
        select(Alert).where(Alert.id.in_(select(EsitoOrizzonte.alert_id)))
    ).scalars()}
    calcolo = _Calcolo(db, min(r.ancora for r in righe))
    cambiate = 0
    for aid, gruppo in per_alert.items():
        a = alert.get(aid)
        if a is None:
            continue
        nuovi = calcolo.esiti(a, gruppo[0].tono, gruppo[0].ancora, [r.orizzonte for r in gruppo])
        for r in gruppo:
            v = nuovi.get(r.orizzonte)
            if v is None:
                continue  # serie accorciata da una riparazione: si tiene il valore
            if any(_diverso(getattr(r, k), x) for k, x in v.items()):
                for k, x in v.items():
                    setattr(r, k, x)
                r.metodo = METODO
                cambiate += 1
    if commit and cambiate:
        db.commit()
    logger.info(f"[esiti-orizzonti] riallineate {cambiate} righe su {len(righe)}")
    return len(righe), cambiate


# ─── Lettura per il cubo ────────────────────────────────────────────────────

def _intervallo(
    coppie: list[tuple[date, int]], h: int,
) -> tuple[float | None, float | None, float | None]:
    """(tasso %, basso, alto) dimensionato sulle finestre indipendenti."""
    if not coppie:
        return None, None, None
    tasso = sum(c for _, c in coppie) / len(coppie) * 100.0
    lo, hi = sized_interval(
        rate_pct=tasso, effective_n=independent_blocks([d for d, _ in coppie], h),
    )
    return round(tasso, 1), lo, hi


def cella(righe: list, orizzonte: int, proprio: bool, min_n: int) -> dict:
    """Una riga della tabella «per orizzonte» di un detector."""
    mediana = [(r.ancora, r.colpo_mediana) for r in righe if r.colpo_mediana is not None]
    controllo = [(r.ancora, r.colpo_controllo) for r in righe if r.colpo_controllo is not None]
    t_m, lo_m, hi_m = _intervallo(mediana, orizzonte)
    t_c, lo_c, hi_c = _intervallo(controllo, orizzonte)
    per_giorno, giorni = tasso_per_giorno(controllo)
    ecc = [r.eccesso_controllo for r in righe if r.eccesso_controllo is not None]
    eff = independent_blocks([r.ancora for r in righe], orizzonte)
    verdetto = None
    if proprio and t_c is not None:
        verdetto = "above" if lo_c > 50.0 else "below" if hi_c < 50.0 else "inconclusive"
    return {
        "orizzonte": orizzonte,
        "proprio": proprio,
        "n": len(righe),
        "effective_n": eff,
        "giorni": giorni,
        "colpo_mediana": t_m,
        "colpo_mediana_ci_low": lo_m,
        "colpo_mediana_ci_high": hi_m,
        "colpo_controllo": t_c,
        "colpo_controllo_ci_low": lo_c,
        "colpo_controllo_ci_high": hi_c,
        "colpo_controllo_per_giorno": per_giorno,
        "eccesso_controllo_medio": round(sum(ecc) / len(ecc) * 100.0, 2) if ecc else None,
        "verdetto": verdetto,
        "low_confidence": eff < min_n,
    }


def celle_per_detector(db: Session, *, min_n: int) -> dict[str, list[dict]]:
    """{detector: celle per orizzonte, dal piu' corto}."""
    righe = db.execute(select(
        EsitoOrizzonte.detector, EsitoOrizzonte.orizzonte, EsitoOrizzonte.ancora,
        EsitoOrizzonte.colpo_mediana, EsitoOrizzonte.colpo_controllo,
        EsitoOrizzonte.eccesso_controllo,
    )).all()
    gruppi: dict[tuple[str, int], list] = defaultdict(list)
    for r in righe:
        gruppi[(r.detector, r.orizzonte)].append(r)
    out: dict[str, list[dict]] = defaultdict(list)
    for (det, h), gr in sorted(gruppi.items()):
        out[det].append(cella(gr, h, h == _horizon_days(det), min_n))
    return dict(out)
