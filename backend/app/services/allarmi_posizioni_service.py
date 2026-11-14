"""Gli avvisi sulle posizioni eToro aperte (FA-146): stop vicino e mossa anomala.

Gira subito dopo la sincronizzazione con eToro (ogni 10 minuti), col prezzo
che eToro ha appena dato: nessuna chiamata a Yahoo per il prezzo.

⚠️ Le soglie sono in ATR, cioe' nella volatilita' dello strumento, e quella
dello stop vicino e' 0,5 ATR e non 1. Misurato il 2026-11-14 sulle posizioni
vere: le tre su SOXL stavano gia' fra 0,64 e 0,77 ATR dallo stop, quindi a 1
ATR l'avviso sarebbe suonato ogni giorno per settimane. Un allarme che suona
sempre insegna a ignorarlo (CLAUDE.md, la pastiglia «in ritardo»). Le soglie
sono impostazioni: `TELEGRAM_POSIZIONI_STOP_ATR`, `TELEGRAM_POSIZIONI_MOSSA_ATR`.

Una notifica per posizione, per tipo e per giorno, registrata in
`novita_notificate`. A mercato chiuso niente: il prezzo e' quello della
chiusura e una «mossa» rispetto a ieri sarebbe gia' stata detta.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EtoroPosizione, EtoroStrumento, NovitaNotificata, OhlcvDaily, Stock
from app.services import rischio_posizioni_service as rp

#: Il prezzo di eToro conta come «di seduta» se e' piu' recente di cosi'.
_FRESCO = timedelta(minutes=30)


@dataclass(frozen=True)
class Avviso:
    position_id: int
    ticker: str
    tipo: str            # "stop_vicino" | "mossa"
    lato: str
    prezzo: float
    stop: float | None
    distanza_pct: float | None
    distanza_atr: float | None
    variazione_pct: float | None
    variazione_atr: float | None


def valuta(
    *, prezzo: float, chiusura_prec: float | None, stop: float | None, lato: str,
    atr: float | None, soglia_stop_atr: float, soglia_mossa_atr: float,
) -> dict[str, dict]:
    """{tipo: misure} degli avvisi che scattano. Puro.

    Stop vicino: distanza dallo stop entro `soglia_stop_atr` ATR, e ancora
    positiva (oltre lo stop la posizione si chiude, e lo dice la notifica di
    chiusura). Mossa: variazione dalla chiusura precedente oltre
    `soglia_mossa_atr` ATR, in qualunque direzione."""
    out: dict[str, dict] = {}
    if not atr or atr <= 0 or prezzo <= 0:
        return out
    if stop and stop > 0:
        d = (prezzo - stop) if lato == "long" else (stop - prezzo)
        if 0 < d <= soglia_stop_atr * atr:
            out["stop_vicino"] = {"distanza_pct": d / prezzo, "distanza_atr": d / atr}
    if chiusura_prec and chiusura_prec > 0:
        v = prezzo - chiusura_prec
        if abs(v) >= soglia_mossa_atr * atr:
            out["mossa"] = {"variazione_pct": v / chiusura_prec, "variazione_atr": v / atr}
    return out


def chiave(position_id: int, tipo: str, giorno: date) -> str:
    return hashlib.sha1(f"posizione:{position_id}:{tipo}:{giorno.isoformat()}".encode()).hexdigest()


def _barre_recenti(db: Session, stock: Stock | None, simbolo: str | None) -> list[rp.Barra]:
    if stock is not None:
        righe = db.execute(
            select(OhlcvDaily.date, OhlcvDaily.high, OhlcvDaily.low, OhlcvDaily.close)
            .where(OhlcvDaily.stock_id == stock.id)
            .order_by(OhlcvDaily.date.desc()).limit(40)
        ).all()
        return [rp.Barra(str(d)[:10], float(h), float(lo), float(c)) for d, h, lo, c in reversed(righe)]
    return rp._barre_yahoo(simbolo)[-40:] if simbolo else []


def mercato_aperto(ticker: str) -> bool:
    """Per un titolo USA (senza suffisso di borsa) la seduta regolare; per gli
    altri decide la freschezza del prezzo di eToro."""
    if "." in ticker:
        return True
    from app.services import premarket_service  # noqa: PLC0415
    return premarket_service.us_market_open_now()


def da_avvisare(
    db: Session, *, soglia_stop_atr: float, soglia_mossa_atr: float,
    adesso: datetime | None = None, aperto: Callable[[str], bool] = mercato_aperto,
) -> list[Avviso]:
    """Gli avvisi da mandare ora: soglie superate, prezzo di seduta, non gia'
    mandati oggi."""
    adesso = adesso or datetime.now(UTC)
    oggi = adesso.date()
    righe = db.execute(
        select(EtoroPosizione, EtoroStrumento, Stock)
        .join(EtoroStrumento, EtoroStrumento.instrument_id == EtoroPosizione.instrument_id)
        .outerjoin(Stock, Stock.id == EtoroStrumento.stock_id)
        .where(EtoroPosizione.chiusa_il.is_(None))
    ).all()
    gia = set(db.execute(select(NovitaNotificata.chiave)).scalars())
    barre_per: dict[int, list[rp.Barra]] = {}
    out: list[Avviso] = []
    for p, s, st in righe:
        quando = p.pnl_il
        if p.prezzo_corrente is None or quando is None:
            continue
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=UTC)
        if adesso - quando > _FRESCO:
            continue   # prezzo non di seduta
        ticker = (st.ticker if st else None) or s.simbolo or f"#{s.instrument_id}"
        if not aperto(ticker):
            continue
        if s.instrument_id not in barre_per:
            barre_per[s.instrument_id] = _barre_recenti(db, st, s.simbolo)
        barre = barre_per[s.instrument_id]
        prec = [b for b in barre if b.data < oggi.isoformat()]
        a = rp.atr(prec)
        scattati = valuta(
            prezzo=p.prezzo_corrente, chiusura_prec=prec[-1].chiusura if prec else None,
            stop=p.stop, lato=p.lato, atr=a,
            soglia_stop_atr=soglia_stop_atr, soglia_mossa_atr=soglia_mossa_atr,
        )
        for tipo, m in scattati.items():
            if chiave(p.position_id, tipo, oggi) in gia:
                continue
            out.append(Avviso(
                position_id=p.position_id, ticker=ticker, tipo=tipo, lato=p.lato,
                prezzo=p.prezzo_corrente, stop=p.stop,
                distanza_pct=m.get("distanza_pct"), distanza_atr=m.get("distanza_atr"),
                variazione_pct=m.get("variazione_pct"), variazione_atr=m.get("variazione_atr"),
            ))
    return out


def segna(db: Session, avvisi: list[Avviso], giorno: date) -> None:
    for a in avvisi:
        k = chiave(a.position_id, a.tipo, giorno)
        if db.get(NovitaNotificata, k) is None:
            db.add(NovitaNotificata(chiave=k))
    db.commit()
