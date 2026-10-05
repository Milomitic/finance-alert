"""Negoziabile su eToro, e quanto costa (FA-126).

Due cose:

1. **Quali titoli del catalogo si negoziano su eToro.** Si chiedono a eToro i
   simboli del catalogo, 100 per chiamata, con le varianti di simbolo che eToro
   usa: lo stesso ticker (ENI.MI si risolve cosi', misurato il 2026-10-06), il
   suffisso «.US» di alcuni ETF americani, e la classe col punto (BRK-B ->
   BRK.B). Non il contrario: il catalogo eToro ha oltre 40.000 strumenti fra
   azioni ed ETF, e scaricarlo tutto costerebbe minuti per sapere di mille.

2. **Il costo vero di un ingresso.** `/trading/info/costs` rende commissione,
   ricarico, spread e overnight PER NOTTE di un ordine ipotetico. ⚠️ La
   risposta vera porta l'importo nel campo `value`, la specifica dice
   `amount`: si leggono entrambi. E l'overnight di un titolo europeo arriva
   in EUR: si converte in USD col servizio dei cambi, e se il cambio manca il
   valore resta nella sua valuta invece di diventare dollari per finta.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Stock
from app.models.etoro import EtoroCatalogo
from app.services import etoro_client, fx_service

_STRUMENTI = "/api/v2/market-data/instruments"
_COSTI = "/api/v2/trading/info/costs"
_LOTTO = 100

#: Le voci di costo d'apertura (una volta) e quelle di detenzione (a notte).
APERTURA = ("transactionFee", "markup", "marketSpread", "sdrt")
NOTTE = "overnightFee"
WEEKEND = "overWeekendFee"

_CACHE_COSTI_S = 3600.0
_cache_costi: dict[tuple, tuple[float, Any]] = {}
_lock = threading.Lock()


def varianti(ticker: str) -> list[str]:
    """Le forme in cui eToro puo' scrivere un ticker del catalogo, in ordine di
    preferenza: la prima trovata vince."""
    t = ticker.strip().upper()
    out = [t]
    m = re.fullmatch(r"([A-Z0-9]+)-([A-Z])", t)
    if m:
        out.append(f"{m.group(1)}.{m.group(2)}")
    if "." not in t and "-" not in t:
        out.append(f"{t}.US")
    return out


def aggiorna(db: Session, *, adesso: datetime | None = None) -> tuple[int, int]:
    """Rifa' la tabella. Rende (trovati, cercati). Se una chiamata fallisce
    solleva PRIMA di toccare la tabella: un elenco parziale direbbe «non su
    eToro» di titoli che lo sono."""
    adesso = adesso or datetime.now(UTC)
    titoli = db.execute(select(Stock.id, Stock.ticker)).all()
    per_variante: dict[str, list[tuple[int, int]]] = {}
    for sid, ticker in titoli:
        for prio, v in enumerate(varianti(ticker)):
            per_variante.setdefault(v, []).append((sid, prio))
    simboli = sorted(per_variante)
    trovati: dict[str, dict] = {}
    for i in range(0, len(simboli), _LOTTO):
        lotto = simboli[i:i + _LOTTO]
        dati = etoro_client.get(_STRUMENTI, op="strumenti", params={"symbols": ",".join(lotto), "pageSize": _LOTTO})
        for r in (dati.get("results") if isinstance(dati, dict) else None) or []:
            if isinstance(r, dict) and isinstance(r.get("instrumentId"), int) and r.get("symbol"):
                trovati.setdefault(str(r["symbol"]).upper(), r)
    scelta: dict[int, tuple[int, dict]] = {}
    for simbolo, r in trovati.items():
        for sid, prio in per_variante.get(simbolo, []):
            if sid not in scelta or prio < scelta[sid][0]:
                scelta[sid] = (prio, r)
    db.execute(delete(EtoroCatalogo))
    for sid, (_, r) in scelta.items():
        db.add(EtoroCatalogo(
            stock_id=sid, instrument_id=r["instrumentId"], simbolo=str(r["symbol"])[:32],
            nome=(r.get("displayName") or None), tipo=(r.get("type") or None), verificato_il=adesso,
        ))
    db.commit()
    return len(scelta), len(titoli)


def vuoto(db: Session) -> bool:
    return db.execute(select(func.count()).select_from(EtoroCatalogo)).scalar_one() == 0


def filtro_su_etoro(stock_id: ColumnElement) -> ColumnElement:
    return stock_id.in_(select(EtoroCatalogo.stock_id))


def del_titolo(db: Session, ticker: str) -> EtoroCatalogo | None:
    return db.execute(
        select(EtoroCatalogo).join(Stock, Stock.id == EtoroCatalogo.stock_id)
        .where(func.upper(Stock.ticker) == ticker.strip().upper()).limit(1)
    ).scalars().first()


# ─── I costi ────────────────────────────────────────────────────────────────


@dataclass
class Voce:
    tipo: str
    importo: float
    valuta: str
    #: None se il cambio non e' noto: l'importo resta nella sua valuta.
    importo_usd: float | None


@dataclass
class Costi:
    simbolo: str
    voci: list[Voce] = field(default_factory=list)
    #: Commissione + ricarico + spread (+ tasse), una volta, in USD.
    apertura_usd: float | None = None
    #: L'overnight di una notte, in USD.
    notte_usd: float | None = None
    weekend_usd: float | None = None
    aggiornato_il: str | None = None


def _somma(voci: list[Voce], tipi: tuple[str, ...]) -> float | None:
    scelte = [v for v in voci if v.tipo in tipi]
    if not scelte:
        return 0.0
    if any(v.importo_usd is None for v in scelte):
        return None
    return sum(v.importo_usd for v in scelte)


def costi(db: Session, ticker: str, *, lato: str, leva: int, importo: float, stop: float | None,
          ora=time.monotonic) -> Costi | None:
    """Il preventivo di un ingresso; None se il titolo non e' su eToro."""
    riga = del_titolo(db, ticker)
    if riga is None:
        return None
    chiave = (riga.instrument_id, lato, leva, round(importo, 2), round(stop or 0.0, 4))
    with _lock:
        in_cache = _cache_costi.get(chiave)
        if in_cache and ora() - in_cache[0] < _CACHE_COSTI_S:
            return in_cache[1]
    corpo: dict[str, Any] = {
        "action": "open", "transaction": "buy" if lato == "long" else "sellShort",
        "instrumentId": riga.instrument_id, "settlementType": "cfd", "orderType": "mkt",
        "leverage": max(int(leva), 1), "amount": float(importo), "orderCurrency": "usd",
    }
    # Lo stop e' obbligatorio con leva > 1 o allo scoperto.
    if stop is not None and stop > 0:
        corpo["stopLossRate"] = float(stop)
    dati = etoro_client.post_lettura(_COSTI, corpo, op="costi")
    voci = []
    for c in (dati.get("costs") if isinstance(dati, dict) else None) or []:
        if not isinstance(c, dict) or not c.get("costType"):
            continue
        valore = c.get("value", c.get("amount"))
        try:
            valore = float(valore)
        except (TypeError, ValueError):
            continue
        valuta = (c.get("currency") or "USD").upper()
        usd = valore if valuta == "USD" else fx_service.to_usd(valore, valuta)
        voci.append(Voce(tipo=c["costType"], importo=valore, valuta=valuta, importo_usd=usd))
    esito = Costi(
        simbolo=riga.simbolo, voci=voci,
        apertura_usd=_somma(voci, APERTURA), notte_usd=_somma(voci, (NOTTE,)),
        weekend_usd=_somma(voci, (WEEKEND,)),
        aggiornato_il=(dati.get("lastUpdated") if isinstance(dati, dict) else None),
    )
    with _lock:
        _cache_costi[chiave] = (ora(), esito)
    return esito


def svuota_cache() -> None:
    with _lock:
        _cache_costi.clear()
