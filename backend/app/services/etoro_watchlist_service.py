"""Le watchlist eToro diventano preferiti (FA-125).

Una lettura di `/api/v1/watchlists` (tutte le watchlist con i loro elementi),
gli strumenti abbinati al catalogo con la stessa regola delle posizioni
(`etoro_portafoglio_service.abbina`: simbolo identico E nome compatibile), e i
titoli abbinati diventano preferiti con origine «etoro».

Cinque regole:

1. **«Recently Invested» resta fuori.** E' la lista dei titoli toccati in
   passato, non di quelli scelti: 111 il 2026-10-06, scelta dell'utente.
2. **Si aggiungono e si tolgono SOLO i preferiti nati da eToro.** Una stella
   messa a mano non si tocca mai, anche se il titolo sparisce da eToro.
3. **Una stella tolta a mano resta tolta** (`PreferitoEscluso`), finche' il
   titolo e' nelle watchlist; rimetterla la rende manuale.
4. **Si toglie solo se la lettura e' completa.** Se una watchlist inclusa
   rende meno elementi di quanti ne dichiara (`totalItems`), o nessuna
   watchlist inclusa ha elementi, il giro aggiunge e basta: una lettura
   parziale non deve cancellare preferiti.
5. **Una risposta senza `watchlists` e' un errore**, non zero watchlist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.errors import UpstreamUnavailable
from app.models.etoro import EtoroStrumento
from app.models.preferito import Preferito, PreferitoEscluso
from app.services import etoro_client, preferiti_service
from app.services.etoro_portafoglio_service import aggiorna_strumenti

_WATCHLIST = "/api/v1/watchlists"
#: I tipi di watchlist che non diventano preferiti.
TIPI_ESCLUSI = frozenset({"RecentlyInvested"})


@dataclass
class EsitoWatchlist:
    saltata: str | None = None
    watchlist: int = 0
    strumenti: int = 0
    abbinati: int = 0
    aggiunti: int = 0
    tolti: int = 0
    completa: bool = True


def _incluse(dati: Any) -> list[dict]:
    lista = dati.get("watchlists") if isinstance(dati, dict) else None
    if not isinstance(lista, list):
        raise UpstreamUnavailable("eToro: risposta senza watchlists", source="etoro", op="watchlist")
    return [w for w in lista if isinstance(w, dict) and w.get("watchlistType") not in TIPI_ESCLUSI]


def _strumenti(watchlist: list[dict]) -> tuple[set[int], bool]:
    """Gli id degli strumenti (non le persone) e se la lettura e' completa."""
    ids: set[int] = set()
    completa = True
    for w in watchlist:
        items = [it for it in (w.get("items") or []) if isinstance(it, dict)]
        dichiarati = w.get("totalItems")
        if isinstance(dichiarati, int) and len(items) < dichiarati:
            completa = False
        for it in items:
            if it.get("itemType") != "Instrument":
                continue
            try:
                ids.add(int(it.get("itemId")))
            except (TypeError, ValueError):
                continue
    return ids, completa and bool(ids)


def preferito_da_conferma(db: Session, s: EtoroStrumento) -> bool:
    """Dopo una conferma dell'utente: se lo strumento e' in una watchlist,
    il preferito nasce subito invece che al giro successivo. True se nato."""
    if not s.in_watchlist or s.stock_id is None:
        return False
    if db.get(Preferito, s.stock_id) is not None or db.get(PreferitoEscluso, s.stock_id) is not None:
        return False
    db.add(Preferito(stock_id=s.stock_id, aggiunto_il=datetime.now(UTC), origine=preferiti_service.ETORO))
    db.commit()
    return True


def sincronizza_watchlist(db: Session, *, adesso: datetime | None = None) -> EsitoWatchlist:
    if not etoro_client.configurato():
        return EsitoWatchlist(saltata="non configurato")
    adesso = adesso or datetime.now(UTC)
    watchlist = _incluse(etoro_client.get(_WATCHLIST, op="watchlist"))
    ids, completa = _strumenti(watchlist)
    esito = EsitoWatchlist(watchlist=len(watchlist), strumenti=len(ids), completa=completa)
    if ids:
        aggiorna_strumenti(db, ids, adesso)
    db.execute(update(EtoroStrumento).values(in_watchlist=EtoroStrumento.instrument_id.in_(ids or {-1})))

    voluti = set(db.execute(
        select(EtoroStrumento.stock_id).where(
            EtoroStrumento.instrument_id.in_(ids or {-1}), EtoroStrumento.stock_id.is_not(None)
        )
    ).scalars())
    esito.abbinati = len(voluti)
    esistenti = dict(db.execute(select(Preferito.stock_id, Preferito.origine)).all())
    esclusi = set(db.execute(select(PreferitoEscluso.stock_id)).scalars())

    for sid in sorted(voluti - set(esistenti) - esclusi):
        db.add(Preferito(stock_id=sid, aggiunto_il=adesso, origine=preferiti_service.ETORO))
        esito.aggiunti += 1
    if completa:
        da_togliere = [sid for sid, o in esistenti.items() if o == preferiti_service.ETORO and sid not in voluti]
        if da_togliere:
            esito.tolti = db.execute(delete(Preferito).where(Preferito.stock_id.in_(da_togliere))).rowcount
        # Un'esclusione serve solo finche' il titolo e' in una watchlist.
        db.execute(delete(PreferitoEscluso).where(PreferitoEscluso.stock_id.notin_(voluti or {-1})))
    db.commit()
    return esito
