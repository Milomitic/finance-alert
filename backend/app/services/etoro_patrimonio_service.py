"""Il patrimonio del conto eToro nel tempo (FA-127).

Tre fonti, ognuna per cio' che sa fare:

- `/balances/history`: il valore a fine giornata degli ultimi 12 mesi, conto
  Trading. eToro non va oltre i 12 mesi, quindi si salva qui (`recupera`).
- La sincronizzazione dei 10 minuti e la lettura dal vivo: la riga di oggi e i
  punti della curva di oggi (`fotografa`).
- Lo storico delle operazioni chiuse: i profitti realizzati, per il rendimento.

⚠️ Il valore del conto comprende versamenti e prelievi, e da quella sola curva
non si separano dalle perdite: misurato il 2026-10-06, il conto passa da 17.800
a 2.250 USD in sei mesi e risale a 8.660 con l'investito che triplica. Il
rendimento di un periodo quindi NON e' la variazione del valore: e' il P/L
GENERATO, cioe' i profitti chiusi nel periodo piu' la variazione del P/L
aperto. Non dipende da quanto si e' versato. La differenza fra la variazione
del valore e il generato sono i flussi (versamenti meno prelievi), ricavati per
differenza e dichiarati come tali: ci finiscono anche arrotondamenti e
commissioni che il P/L di eToro non porta.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.etoro import (
    EtoroConto,
    EtoroOperazione,
    EtoroPatrimonioGiorno,
    EtoroPosizione,
    EtoroPuntoIntraday,
    EtoroStrumento,
)
from app.services import etoro_client
from app.services.etoro_portafoglio_service import ROMA, _aware, _num, _ts, mezzanotte_di_roma_utc

STORICO = "storico"
VIVO = "vivo"
FONTI = (STORICO, VIVO)

_STORICO_SALDI = "/api/v1/balances/history"
_STORICO_OPERAZIONI = "/api/v1/trading/info/trade/history"
_AGGREGATO = "/api/v1/trading/info/aggregate-portfolio"
_GIORNI_STORICO = 364
_PAGINE_OPERAZIONI = 20
_RIGHE_PAGINA = 100
#: Un punto intraday al minuto al massimo, tenuto tre giorni.
_PASSO_INTRADAY = timedelta(seconds=60)
_TIENI_INTRADAY = timedelta(days=3)
#: La lettura dal vivo si rifa' al massimo ogni 30 s: con la home aperta su
#: due schede sono comunque due chiamate al minuto contro le 60 concesse.
CACHE_VIVO_S = 30.0

#: I periodi del rendimento: chiave -> giorni (None = da inizio anno).
PERIODI: dict[str, int | None] = {"1S": 7, "1M": 30, "3M": 90, "YTD": None, "1A": 365}


def giorno_di_roma(istante: datetime) -> date:
    return istante.astimezone(ROMA).date()


# ─── Recupero dello storico ─────────────────────────────────────────────────


def _trading(snapshot: dict) -> dict | None:
    for a in snapshot.get("accountSnapshots") or []:
        if isinstance(a, dict) and a.get("accountType") == "Trading":
            return a
    return None


def recupera(db: Session, *, adesso: datetime | None = None) -> tuple[int, int]:
    """I 12 mesi di fine giornata e le operazioni chiuse. Rende (giorni, operazioni).
    La riga di oggi resta quella «viva»: eToro la fotografa solo a giorno chiuso."""
    adesso = adesso or datetime.now(UTC)
    oggi = giorno_di_roma(adesso)
    dal = oggi - timedelta(days=_GIORNI_STORICO)
    dati = etoro_client.get(_STORICO_SALDI, op="patrimonio", params={
        "fromDate": dal.isoformat(), "toDate": oggi.isoformat(), "displayCurrency": "USD",
    })
    giorni = 0
    for s in (dati.get("snapshots") if isinstance(dati, dict) else None) or []:
        conto = _trading(s) if isinstance(s, dict) else None
        try:
            g = date.fromisoformat(str(s.get("date"))[:10])
        except (ValueError, AttributeError):
            continue
        valore = _num(conto.get("displayTotal")) if conto else None
        if conto is None or valore is None or g >= oggi:
            continue
        riga = db.get(EtoroPatrimonioGiorno, g) or EtoroPatrimonioGiorno(giorno=g)
        riga.valore = valore
        riga.cassa = _num(conto.get("displayCash"))
        riga.investito = _num(conto.get("displayInvestedAmount"))
        riga.pnl_aperto = _num(conto.get("displayPnl"))
        riga.fonte = STORICO
        riga.aggiornato_il = adesso
        db.merge(riga)
        giorni += 1
    operazioni = 0
    for pagina in range(1, _PAGINE_OPERAZIONI + 1):
        righe = etoro_client.get(_STORICO_OPERAZIONI, op="storico", params={
            "minDate": dal.isoformat(), "page": pagina, "pageSize": _RIGHE_PAGINA,
        })
        righe = righe if isinstance(righe, list) else []
        for r in righe:
            if salva_operazione(db, r):
                operazioni += 1
        if len(righe) < _RIGHE_PAGINA:
            break
    db.commit()
    return giorni, operazioni


def salva_operazione(db: Session, r: Any) -> bool:
    if not isinstance(r, dict) or not isinstance(r.get("positionId"), int):
        return False
    chiusa = _ts(r.get("closeTimestamp"))
    profitto = _num(r.get("netProfit"))
    if chiusa is None or profitto is None:
        return False
    aperta = _ts(r.get("openTimestamp"))
    # In UTC: SQLite conserva l'istante senza fuso, e i confronti dei periodi
    # devono stare su un orologio solo.
    chiusa = chiusa.astimezone(UTC)
    db.merge(EtoroOperazione(
        position_id=r["positionId"], instrument_id=int(r.get("instrumentId") or 0),
        aperta_il=aperta.astimezone(UTC) if aperta else None, chiusa_il=chiusa,
        lato="long" if r.get("isBuy", True) else "short", leva=int(r.get("leverage") or 1),
        prezzo_apertura=_num(r.get("openRate")), prezzo_chiusura=_num(r.get("closeRate")),
        investimento_usd=_num(r.get("investment")), profitto_netto_usd=profitto,
        commissioni_usd=_num(r.get("fees")),
    ))
    return True


def ha_storico(db: Session) -> bool:
    return db.execute(
        select(EtoroPatrimonioGiorno.giorno).where(EtoroPatrimonioGiorno.fonte == STORICO).limit(1)
    ).first() is not None


# ─── La riga di oggi e i punti della curva ──────────────────────────────────


def fotografa(db: Session, valore: float | None, cassa: float | None, pnl: float | None,
              guadagno_giorno: float | None, adesso: datetime) -> bool:
    """Aggiorna la riga di oggi e aggiunge un punto alla curva di oggi.
    Non fa commit: la chiama chi ha gia' una transazione aperta."""
    if valore is None:
        return False
    oggi = giorno_di_roma(adesso)
    riga = db.get(EtoroPatrimonioGiorno, oggi)
    if riga is None:
        riga = EtoroPatrimonioGiorno(giorno=oggi, fonte=VIVO, valore=valore, aggiornato_il=adesso)
        db.add(riga)
    if riga.fonte == VIVO:
        riga.valore = valore
        riga.cassa = cassa
        riga.pnl_aperto = pnl
        riga.investito = valore - (cassa or 0.0) - (pnl or 0.0)
        riga.aggiornato_il = adesso
    ultimo = db.execute(select(func.max(EtoroPuntoIntraday.istante))).scalar()
    if ultimo is None or adesso - _aware(ultimo) >= _PASSO_INTRADAY:
        db.add(EtoroPuntoIntraday(istante=adesso, valore=valore, guadagno_giorno=guadagno_giorno))
        db.execute(delete(EtoroPuntoIntraday).where(EtoroPuntoIntraday.istante < adesso - _TIENI_INTRADAY))
    return True


# ─── La lettura dal vivo ────────────────────────────────────────────────────


@dataclass
class StrumentoOggi:
    instrument_id: int
    ticker: str | None
    simbolo: str | None
    nome: str | None
    guadagno_giorno: float | None
    pnl: float | None
    esposizione: float | None
    margine: float | None


@dataclass
class Vivo:
    aggiornato_il: datetime
    #: True quando eToro non ha risposto e i numeri sono dell'ultima sincronizzazione.
    in_ritardo: bool
    valuta: str | None
    valore: float | None
    valore_ieri: float | None
    guadagno_giorno: float | None
    guadagno_giorno_pct: float | None
    pnl_aperto: float | None
    margine_usato: float | None
    cassa: float | None
    esposizione: float | None
    posizioni: int
    strumenti: list[StrumentoOggi] = field(default_factory=list)


_cache: dict[str, Any] = {"quando": 0.0, "vivo": None}
_lock = threading.Lock()


def _strumenti(db: Session, aggregati: list[dict]) -> list[StrumentoOggi]:
    out = []
    for a in aggregati:
        if not isinstance(a, dict) or not isinstance(a.get("instrumentId"), int):
            continue
        s = db.get(EtoroStrumento, a["instrumentId"])
        ticker = None
        if s is not None and s.stock_id:
            from app.models import Stock

            st = db.get(Stock, s.stock_id)
            ticker = st.ticker if st else None
        out.append(StrumentoOggi(
            instrument_id=a["instrumentId"], ticker=ticker,
            simbolo=s.simbolo if s else None, nome=s.nome if s else None,
            guadagno_giorno=_num(a.get("dailyGainAccountCurrency")),
            pnl=_num(a.get("accountCurrencyReturn")),
            esposizione=_num(a.get("netCurrentExposureAccountCurrency")),
            margine=_num(a.get("totalMarginAccountCurrency")),
        ))
    return sorted(out, key=lambda x: -abs(x.guadagno_giorno or 0.0))


def _posizioni_aperte(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(EtoroPosizione).where(EtoroPosizione.chiusa_il.is_(None))
    ).scalar_one()


def _dal_db(db: Session) -> Vivo | None:
    conto = db.get(EtoroConto, 1)
    if conto is None:
        return None
    esposizione = db.execute(
        select(func.sum(EtoroPosizione.esposizione_usd)).where(EtoroPosizione.chiusa_il.is_(None))
    ).scalar()
    margine = db.execute(
        select(func.sum(EtoroPosizione.margine_usd)).where(EtoroPosizione.chiusa_il.is_(None))
    ).scalar()
    return Vivo(
        aggiornato_il=_aware(conto.aggiornato_il), in_ritardo=True, valuta=conto.valuta,
        valore=conto.valore_totale, valore_ieri=None, guadagno_giorno=conto.guadagno_giorno,
        guadagno_giorno_pct=conto.guadagno_giorno_pct, pnl_aperto=conto.pnl_aperto,
        margine_usato=margine, cassa=conto.credito_usd, esposizione=esposizione,
        posizioni=_posizioni_aperte(db),
    )


def vivo(db: Session, *, adesso: datetime | None = None, ora=time.monotonic) -> Vivo | None:
    """Il conto adesso, da eToro, con una cache di `CACHE_VIVO_S`. Se eToro non
    risponde rende l'ultima sincronizzazione segnata `in_ritardo`; None se non
    c'e' mai stata. Ogni lettura riuscita aggiorna la riga e la curva di oggi."""
    with _lock:
        if _cache["vivo"] is not None and ora() - _cache["quando"] < CACHE_VIVO_S:
            return _cache["vivo"]
        adesso = adesso or datetime.now(UTC)
        try:
            dati = etoro_client.get(_AGGREGATO, op="portafoglio", params={
                "pnlLevel": "DailyPnl",
                "dailyCutoffUtc": mezzanotte_di_roma_utc(adesso).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            tot = dati.get("accountTotals") if isinstance(dati, dict) else None
            if not isinstance(tot, dict):
                raise ValueError("risposta senza accountTotals")
        except Exception as e:  # noqa: BLE001 — la home non deve rompersi per eToro
            logger.warning(f"[etoro] lettura dal vivo non riuscita: {e}")
            return _dal_db(db)
        aggregati = [a for a in (dati.get("instrumentAggregates") or []) if isinstance(a, dict)]
        v = Vivo(
            aggiornato_il=_ts(dati.get("timestamp")) or adesso, in_ritardo=False,
            valuta=dati.get("accountCurrency") or None,
            valore=_num(tot.get("accountTotalValue")), valore_ieri=_num(tot.get("yesterdayTotalValue")),
            guadagno_giorno=_num(tot.get("dailyGainAccountCurrency")),
            guadagno_giorno_pct=_num(tot.get("dailyGainAccountCurrencyPercent")),
            pnl_aperto=_num(tot.get("accountCurrentPnl")),
            margine_usato=_num(tot.get("accountTotalUsedMargin")),
            cassa=_num(tot.get("accountAvailableCash")),
            esposizione=sum(_num(a.get("netCurrentExposureAccountCurrency")) or 0.0 for a in aggregati) or None,
            posizioni=_posizioni_aperte(db),
            strumenti=_strumenti(db, aggregati),
        )
        if fotografa(db, v.valore, v.cassa, v.pnl_aperto, v.guadagno_giorno, adesso):
            db.commit()
        _cache.update(quando=ora(), vivo=v)
        return v


def svuota_cache() -> None:
    _cache.update(quando=0.0, vivo=None)


# ─── L'andamento ────────────────────────────────────────────────────────────


@dataclass
class Periodo:
    chiave: str
    dal: date
    valore_iniziale: float
    valore_finale: float
    #: La variazione del valore: comprende versamenti e prelievi.
    variazione: float
    #: Profitti chiusi nel periodo + variazione del P/L aperto.
    generato: float | None
    realizzato: float
    #: variazione - generato: versamenti meno prelievi, ricavati per differenza.
    flussi: float | None
    #: generato / valore iniziale.
    generato_pct: float | None


def _inizio(giorni: list[EtoroPatrimonioGiorno], oggi: date, n: int | None) -> EtoroPatrimonioGiorno | None:
    """La riga di partenza: l'ultimo giorno chiuso PRIMA del periodo, cioe'
    il valore da cui il periodo e' partito. Se lo storico non arriva cosi'
    indietro, il primo giorno disponibile."""
    soglia = date(oggi.year, 1, 1) if n is None else oggi - timedelta(days=n)
    prima = [g for g in giorni if g.giorno <= soglia]
    if prima:
        return prima[-1]
    return giorni[0] if giorni else None


def periodi(db: Session, giorni: list[EtoroPatrimonioGiorno], oggi: date) -> list[Periodo]:
    if len(giorni) < 2:
        return []
    fine = giorni[-1]
    out = []
    for chiave, n in PERIODI.items():
        inizio = _inizio(giorni, oggi, n)
        if inizio is None or inizio.giorno >= fine.giorno:
            continue
        # Le chiuse DOPO la fine della giornata di partenza, in ora di Roma.
        dal_istante = datetime.combine(inizio.giorno + timedelta(days=1), datetime.min.time(), ROMA)
        realizzato = db.execute(
            select(func.coalesce(func.sum(EtoroOperazione.profitto_netto_usd), 0.0))
            .where(EtoroOperazione.chiusa_il >= dal_istante.astimezone(UTC))
        ).scalar_one()
        variazione = fine.valore - inizio.valore
        generato = None
        if fine.pnl_aperto is not None and inizio.pnl_aperto is not None:
            generato = float(realizzato) + (fine.pnl_aperto - inizio.pnl_aperto)
        out.append(Periodo(
            chiave=chiave, dal=inizio.giorno, valore_iniziale=inizio.valore, valore_finale=fine.valore,
            variazione=variazione, generato=generato, realizzato=float(realizzato),
            flussi=None if generato is None else variazione - generato,
            generato_pct=(generato / inizio.valore * 100.0) if generato is not None and inizio.valore else None,
        ))
    return out


def andamento(db: Session, *, adesso: datetime | None = None) -> tuple[
    list[EtoroPatrimonioGiorno], list[EtoroPuntoIntraday], list[Periodo]
]:
    adesso = adesso or datetime.now(UTC)
    oggi = giorno_di_roma(adesso)
    giorni = list(db.execute(
        select(EtoroPatrimonioGiorno)
        .where(EtoroPatrimonioGiorno.giorno >= oggi - timedelta(days=366))
        .order_by(EtoroPatrimonioGiorno.giorno)
    ).scalars())
    inizio_oggi = mezzanotte_di_roma_utc(adesso)
    punti = list(db.execute(
        select(EtoroPuntoIntraday).where(EtoroPuntoIntraday.istante >= inizio_oggi).order_by(EtoroPuntoIntraday.istante)
    ).scalars())
    return giorni, punti, periodi(db, giorni, oggi)
