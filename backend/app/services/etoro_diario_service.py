"""Il diario delle operazioni chiuse su eToro, legato ai segnali (FA-128).

Le operazioni vengono dallo storico di eToro (`etoro_operazioni`, FA-127). Per
ognuna il diario dice se un segnale dell'app l'ha preceduta e, se si', come e'
andata davvero contro il piano di quel segnale.

**Il legame.** Un segnale «precede» un'operazione quando e' sullo stesso
titolo, nella stessa direzione (rialzo -> long, ribasso -> short) ed e' nato
nei cinque giorni di calendario prima dell'apertura (tre sedute, piu' un fine
settimana). Fra piu' candidati vince il piu' vicino. ⚠️ E' una coincidenza
temporale, non una prova che l'operazione sia stata aperta PER quel segnale:
il diario lo chiama «preceduta da», mai «aperta dal».

**L'esito in R.** Per un'operazione legata, R reale = movimento del prezzo
dall'apertura alla chiusura, nel verso dell'operazione, diviso il rischio del
piano (|entry - stop| del magazzino `plan_outcomes`). Accanto, l'R che il piano
ha ottenuto nel magazzino. La leva non entra: R e' una misura del prezzo.

**L'anno in euro.** Il realizzato di ogni operazione si converte al cambio
EUR/USD del giorno di chiusura. ⚠️ Non e' una consulenza fiscale: e' una
somma, utile da passare a chi fa la dichiarazione, che decidera' le regole.

Con poche operazioni i numeri sono indicativi, e il riepilogo lo dice col
conteggio accanto a ogni tasso.
"""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, PlanOutcome, Stock
from app.models.etoro import EtoroOperazione, EtoroStrumento
from app.services.etoro_portafoglio_service import ROMA, _aware

#: Quanto prima dell'apertura un segnale puo' «precedere» un'operazione.
FINESTRA_SEGNALE = timedelta(days=5)
_DIREZIONE = {"long": "bull", "short": "bear"}


@dataclass
class Voce:
    position_id: int
    instrument_id: int
    ticker: str | None
    simbolo: str | None
    aperta_il: datetime | None
    chiusa_il: datetime
    lato: str
    leva: int
    prezzo_apertura: float | None
    prezzo_chiusura: float | None
    investimento_usd: float | None
    profitto_netto_usd: float
    commissioni_usd: float | None
    #: Il profitto in % dell'investito (il margine).
    pct_investimento: float | None
    giorni: float | None
    # ── Il segnale che l'ha preceduta, se c'e' ──
    alert_id: int | None = None
    detector: str | None = None
    segnale_il: datetime | None = None
    r_reale: float | None = None
    r_piano: float | None = None
    esito_piano: str | None = None


@dataclass
class Gruppo:
    n: int
    vincenti: int
    profitto_usd: float
    #: vincenti / n, in %; None sotto le 2 operazioni.
    vincenti_pct: float | None
    profitto_medio_usd: float | None


@dataclass
class Anno:
    anno: int
    n: int
    profitto_usd: float
    #: None se manca il cambio di almeno un giorno: una somma parziale
    #: presentata come totale sarebbe un numero sbagliato con l'aria giusta.
    profitto_eur: float | None
    commissioni_usd: float


@dataclass
class Diario:
    voci: list[Voce] = field(default_factory=list)
    tutte: Gruppo | None = None
    precedute: Gruppo | None = None
    non_precedute: Gruppo | None = None
    r_reale_medio: float | None = None
    r_piano_medio: float | None = None
    con_r: int = 0
    anni: list[Anno] = field(default_factory=list)


# ─── Il cambio EUR/USD del giorno ───────────────────────────────────────────

_cache_cambi: dict[str, object] = {"quando": 0.0, "serie": {}}
_lock_cambi = threading.Lock()
_CACHE_CAMBI_S = 12 * 3600.0


def _scarica_eurusd(dal: date) -> dict[date, float]:
    """Le chiusure EURUSD=X da `dal`, via yfinance. Vuoto se la rete non c'e'."""
    try:
        import yfinance as yf

        df = yf.download("EURUSD=X", start=dal.isoformat(), progress=False, auto_adjust=False, threads=False)
    except Exception as e:  # noqa: BLE001 — il cambio e' un di piu', il diario no
        logger.warning(f"[diario] cambio EUR/USD non scaricato: {e}")
        return {}
    if df is None or df.empty:
        return {}
    chiusure = df["Close"]
    if hasattr(chiusure, "columns"):
        chiusure = chiusure.iloc[:, 0]
    return {i.date(): float(v) for i, v in chiusure.items() if v == v and v > 0}


def cambi_eurusd(dal: date, scarica: Callable[[date], dict[date, float]] = _scarica_eurusd,
                 ora=time.monotonic) -> dict[date, float]:
    with _lock_cambi:
        serie = _cache_cambi["serie"]
        if serie and ora() - _cache_cambi["quando"] < _CACHE_CAMBI_S and min(serie) <= dal:  # type: ignore[arg-type]
            return serie  # type: ignore[return-value]
        nuova = scarica(dal - timedelta(days=7))
        if nuova:
            _cache_cambi.update(quando=ora(), serie=nuova)
        return nuova


def _cambio_del_giorno(serie: dict[date, float], g: date) -> float | None:
    """La chiusura del giorno, o dell'ultimo giorno prima (fine settimana)."""
    for k in range(0, 6):
        v = serie.get(g - timedelta(days=k))
        if v:
            return v
    return None


def svuota_cache() -> None:
    _cache_cambi.update(quando=0.0, serie={})


# ─── Il diario ──────────────────────────────────────────────────────────────


def _tono(alert: Alert) -> str | None:
    try:
        return (json.loads(alert.snapshot or "{}") or {}).get("tone")
    except (TypeError, ValueError):
        return None


def _segnale_che_precede(db: Session, stock_id: int, lato: str, aperta: datetime) -> Alert | None:
    candidati = db.execute(
        select(Alert).where(
            Alert.stock_id == stock_id, Alert.signal_name.is_not(None),
            Alert.emitted_at <= aperta, Alert.emitted_at >= aperta - FINESTRA_SEGNALE,
        ).order_by(Alert.emitted_at.desc())
    ).scalars().all()
    voluto = _DIREZIONE.get(lato)
    for a in candidati:
        if _tono(a) == voluto:
            return a
    return None


def _gruppo(voci: list[Voce]) -> Gruppo:
    n = len(voci)
    vincenti = sum(1 for v in voci if v.profitto_netto_usd > 0)
    totale = sum(v.profitto_netto_usd for v in voci)
    return Gruppo(
        n=n, vincenti=vincenti, profitto_usd=totale,
        vincenti_pct=(vincenti / n * 100.0) if n >= 2 else None,
        profitto_medio_usd=(totale / n) if n else None,
    )


def diario(db: Session, *, cambi: Callable[[date], dict[date, float]] = cambi_eurusd) -> Diario:
    ops = db.execute(select(EtoroOperazione).order_by(EtoroOperazione.chiusa_il.desc())).scalars().all()
    strumenti = {s.instrument_id: s for s in db.execute(select(EtoroStrumento)).scalars()}
    voci: list[Voce] = []
    for op in ops:
        s = strumenti.get(op.instrument_id)
        stock = db.get(Stock, s.stock_id) if s is not None and s.stock_id else None
        aperta = _aware(op.aperta_il) if op.aperta_il else None
        chiusa = _aware(op.chiusa_il)
        v = Voce(
            position_id=op.position_id, instrument_id=op.instrument_id,
            ticker=stock.ticker if stock else None, simbolo=s.simbolo if s else None,
            aperta_il=aperta, chiusa_il=chiusa, lato=op.lato, leva=op.leva,
            prezzo_apertura=op.prezzo_apertura, prezzo_chiusura=op.prezzo_chiusura,
            investimento_usd=op.investimento_usd, profitto_netto_usd=op.profitto_netto_usd,
            commissioni_usd=op.commissioni_usd,
            pct_investimento=(op.profitto_netto_usd / op.investimento_usd * 100.0) if op.investimento_usd else None,
            giorni=((chiusa - aperta).total_seconds() / 86400.0) if aperta else None,
        )
        if stock is not None and aperta is not None:
            a = _segnale_che_precede(db, stock.id, op.lato, aperta)
            if a is not None:
                v.alert_id, v.detector, v.segnale_il = a.id, a.signal_name, _aware(a.emitted_at)
                piano = db.execute(select(PlanOutcome).where(PlanOutcome.alert_id == a.id)).scalars().first()
                if piano is not None:
                    v.r_piano, v.esito_piano = piano.r_multiple, piano.esito
                    rischio = abs(piano.entry - piano.stop)
                    if rischio > 0 and op.prezzo_apertura and op.prezzo_chiusura:
                        segno = 1.0 if op.lato == "long" else -1.0
                        v.r_reale = segno * (op.prezzo_chiusura - op.prezzo_apertura) / rischio
        voci.append(v)

    out = Diario(voci=voci)
    if not voci:
        return out
    out.tutte = _gruppo(voci)
    out.precedute = _gruppo([v for v in voci if v.alert_id is not None])
    out.non_precedute = _gruppo([v for v in voci if v.alert_id is None])
    con_r = [v for v in voci if v.r_reale is not None and v.r_piano is not None]
    out.con_r = len(con_r)
    if con_r:
        out.r_reale_medio = sum(v.r_reale for v in con_r) / len(con_r)  # type: ignore[misc]
        out.r_piano_medio = sum(v.r_piano for v in con_r) / len(con_r)  # type: ignore[misc]

    giorni_chiusura = [v.chiusa_il.astimezone(ROMA).date() for v in voci]
    serie = cambi(min(giorni_chiusura)) if giorni_chiusura else {}
    per_anno: dict[int, list[Voce]] = {}
    for v in voci:
        per_anno.setdefault(v.chiusa_il.astimezone(ROMA).year, []).append(v)
    for anno in sorted(per_anno, reverse=True):
        gruppo = per_anno[anno]
        eur: float | None = 0.0
        for v in gruppo:
            c = _cambio_del_giorno(serie, v.chiusa_il.astimezone(ROMA).date())
            if c is None:
                eur = None
                break
            eur += v.profitto_netto_usd / c  # type: ignore[operator]
        out.anni.append(Anno(
            anno=anno, n=len(gruppo), profitto_usd=sum(v.profitto_netto_usd for v in gruppo),
            profitto_eur=eur, commissioni_usd=sum(v.commissioni_usd or 0.0 for v in gruppo),
        ))
    return out
