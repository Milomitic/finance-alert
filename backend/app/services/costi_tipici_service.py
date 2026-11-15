"""I costi tipici di eToro e l'attesa dei piani al netto (FA-142).

Il pannello Motore dice l'attesa dei piani in R. Un'attesa di +0,05 R puo'
sparire nei costi: la commissione e' circa lo 0,15% del nozionale per lato
(misurato il 2026-11-15, uguale su AAPL e UCG.MI), e su uno stop al 2% vale
gia' 0,15 R andata e ritorno. Il costo in R dipende dalla distanza dello
stop, quindi lo stesso costo pesa molto di piu' sui piani brevi.

Le misure vengono da un preventivo di eToro in SOLA LETTURA
(`etoro_catalogo_service.costi`), una volta a settimana:

- un preventivo long alla leva tipica per ogni titolo negoziabile:
  commissione, spread e notte long, che cambiano da titolo a titolo;
- un preventivo short per cinque titoli per valuta: la notte short e' la
  loro mediana.

⚠️ Tre ipotesi, dichiarate perche' il preventivo non le copre:

1. La chiusura costa quanto l'apertura in commissione. Il preventivo descrive
   solo l'apertura; una stima che le ignorasse sarebbe ottimista.
2. Le notti sono i giorni di CALENDARIO fra ingresso e uscita: il venerdi'
   eToro addebita il fine settimana, cioe' tre notti, e contare sabato e
   domenica come notti normali da' la stessa somma.
3. A leva 1 nessuna notte: eToro non ne addebita (misurato, long e short).
"""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CostoTipico, EtoroCatalogo, EtoroPosizione, Stock

#: Il nozionale del preventivo, in USD: le frazioni non ne dipendono.
IMPORTO = 1000.0
#: La leva se il conto non ne ha ancora una tipica.
LEVA_PREDEFINITA = 5
#: Pausa fra due preventivi. A 0,5 s eToro rispondeva 429 a raffiche e il
#: primo giro (2026-11-15) e' durato 50 minuti con 17 fallimenti.
PAUSA_S = 1.5
#: Quanti titoli per valuta misurano la notte short, che non dipende dal titolo.
CAMPIONE_SHORT = 5
#: Dopo tanti fallimenti di fila il job si ferma: probabilmente un limite.
FALLIMENTI_MAX = 5


def leva_tipica(db: Session) -> int:
    """La mediana delle leve sopra 1 delle posizioni eToro, aperte e chiuse."""
    leve = [int(v) for v in db.execute(
        select(EtoroPosizione.leva).where(EtoroPosizione.leva > 1)).scalars() if v]
    return int(round(median(leve))) if leve else LEVA_PREDEFINITA


@dataclass(frozen=True)
class Costo:
    commissione_pct: float
    spread_pct: float
    notte_long_pct: float | None
    notte_short_pct: float | None


def costo_in_r(
    *, costo: Costo, ingresso: float, r: float, lato: str, notti: int, con_leva: bool,
) -> float | None:
    """Il costo di un trade in multipli di R. None se manca un dato. Pura.

    Frazione del nozionale: due commissioni, uno spread, e le notti solo con
    leva. Diviso per la distanza dello stop come frazione del prezzo."""
    if ingresso <= 0 or r <= 0:
        return None
    pct = 2 * costo.commissione_pct + costo.spread_pct
    if con_leva and notti > 0:
        notte = costo.notte_long_pct if lato == "long" else costo.notte_short_pct
        if notte is None:
            return None
        pct += notti * notte
    return pct / (r / ingresso)


def _frazioni(voci, leva: int) -> dict[str, float]:
    nozionale = IMPORTO * leva
    somma: dict[str, float] = {}
    for v in voci:
        if v.importo_usd is None:
            continue
        somma[v.tipo] = somma.get(v.tipo, 0.0) + v.importo_usd / nozionale
    return somma


def aggiorna(
    db: Session, *, adesso: datetime | None = None, pausa: float = PAUSA_S,
    preventivo: Callable | None = None,
) -> dict[str, int]:
    """Rifa' la tabella. `preventivo` e' `etoro_catalogo_service.costi`,
    sostituibile nei test.

    Un preventivo long alla leva tipica per titolo: commissione e spread
    (frazioni del nozionale uguali a quelle di leva 1, misurato) e la notte
    long DEL TITOLO. La notte short e' la mediana di `CAMPIONE_SHORT` titoli per
    valuta.

    ⚠️ La notte long si legge per titolo e non per valuta. Il 2026-11-15 la
    prima versione prendeva un rappresentante per valuta, il primo in ordine
    alfabetico: per gli USD era «A», con una notte di 0,0502% contro lo
    0,0282% di AAPL, MSFT, JPM, KO e SOXL, e quel numero e' finito su ogni
    titolo in dollari."""
    if preventivo is None:
        from app.services.etoro_catalogo_service import costi as preventivo  # noqa: PLC0415
    adesso = adesso or datetime.now(UTC)
    leva = leva_tipica(db)
    righe = db.execute(
        select(Stock.id, Stock.ticker, Stock.currency)
        .join(EtoroCatalogo, EtoroCatalogo.stock_id == Stock.id)
        .order_by(Stock.ticker)
    ).all()
    out = {"titoli": len(righe), "scritti": 0, "falliti": 0, "valute": 0}
    letti: list[tuple[int, str, dict[str, float]]] = []
    corti: dict[str, list[float]] = defaultdict(list)
    di_fila = 0
    for sid, ticker, valuta in righe:
        chiave_valuta = (valuta or "?").upper()
        try:
            lungo = preventivo(db, ticker, lato="long", leva=leva, importo=IMPORTO, stop=1e-2)
            corto = None
            if len(corti[chiave_valuta]) < CAMPIONE_SHORT:
                corto = preventivo(db, ticker, lato="short", leva=leva, importo=IMPORTO,
                                   stop=1e12)
            di_fila = 0
        except Exception as exc:  # noqa: BLE001 — un titolo non ferma gli altri
            out["falliti"] += 1
            di_fila += 1
            logger.warning(f"[costi] preventivo {ticker} fallito: {exc}")
            if di_fila >= FALLIMENTI_MAX:
                logger.warning("[costi] troppi fallimenti di fila: mi fermo")
                break
            continue
        finally:
            if pausa:
                time.sleep(pausa)
        if corto is not None:
            n = _frazioni(corto.voci, leva).get("overnightFee")
            if n is not None:
                corti[chiave_valuta].append(n)
        if lungo is None:
            continue
        f = _frazioni(lungo.voci, leva)
        if "transactionFee" in f:
            letti.append((sid, chiave_valuta, f))

    mediane = {v: median(xs) for v, xs in corti.items() if xs}
    out["valute"] = len(mediane)
    for sid, chiave_valuta, f in letti:
        valori = dict(
            commissione_pct=f.get("transactionFee", 0.0) + f.get("sdrt", 0.0),
            spread_pct=f.get("marketSpread", 0.0) + f.get("markup", 0.0),
            notte_long_pct=f.get("overnightFee"),
            notte_short_pct=mediane.get(chiave_valuta),
            leva=leva, valuta=chiave_valuta, aggiornato_il=adesso,
        )
        riga = db.get(CostoTipico, sid)
        if riga is None:
            db.add(CostoTipico(stock_id=sid, **valori))
        else:
            for k, v in valori.items():
                setattr(riga, k, v)
        out["scritti"] += 1
    db.commit()
    logger.info(f"[costi] costi tipici aggiornati: {out}")
    return out


def per_titolo(db: Session) -> tuple[dict[int, Costo], int | None]:
    """{stock_id: Costo} e la leva a cui sono misurate le notti."""
    out: dict[int, Costo] = {}
    leve = set()
    for c in db.execute(select(CostoTipico)).scalars():
        out[c.stock_id] = Costo(c.commissione_pct, c.spread_pct, c.notte_long_pct,
                                c.notte_short_pct)
        leve.add(c.leva)
    return out, (max(leve) if leve else None)
