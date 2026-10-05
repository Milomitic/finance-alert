"""La lista dei titoli preferiti (FA-112): leggerla, aggiungere, togliere."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Stock
from app.models.preferito import Preferito, PreferitoEscluso

MANUALE = "manuale"
ETORO = "etoro"
ORIGINI = (MANUALE, ETORO)


def _stock(db: Session, ticker: str) -> Stock | None:
    # `.limit(1)`: la forma difensiva del CLAUDE.md contro i doppioni storici.
    return db.execute(select(Stock).where(Stock.ticker == ticker).limit(1)).scalars().first()


def elenco(db: Session) -> list[tuple[Stock, datetime, str]]:
    """Nell'ordine in cui sono stati aggiunti: la lista resta ferma, e un
    titolo nuovo va in fondo invece di spostare tutti gli altri. Le stelle
    messe a mano prima di quelle arrivate da eToro: sono quelle scelte una a
    una, e una striscia che ne mostra solo le prime le deve mostrare."""
    righe = db.execute(
        select(Stock, Preferito.aggiunto_il, Preferito.origine)
        .join(Preferito, Preferito.stock_id == Stock.id)
        .order_by((Preferito.origine != MANUALE), Preferito.aggiunto_il, Stock.ticker)
    ).all()
    return [(s, a, o) for s, a, o in righe]


def stock_ids(db: Session) -> set[int]:
    """Gli id dei preferiti, per chi ordina o filtra per rilevanza (FA-113)."""
    return set(db.execute(select(Preferito.stock_id)).scalars())


def aggiungi(db: Session, ticker: str) -> tuple[Stock, datetime, str] | None:
    """Idempotente. None se il ticker non e' nel catalogo. Una stella messa a
    mano rende il preferito manuale anche se era arrivato da eToro: la
    sincronizzazione non lo togliera' piu'."""
    stock = _stock(db, ticker)
    if stock is None:
        return None
    riga = db.get(Preferito, stock.id)
    if riga is None:
        riga = Preferito(stock_id=stock.id, aggiunto_il=datetime.now(UTC), origine=MANUALE)
        db.add(riga)
    riga.origine = MANUALE
    db.execute(delete(PreferitoEscluso).where(PreferitoEscluso.stock_id == stock.id))
    db.commit()
    return stock, riga.aggiunto_il, riga.origine


def togli(db: Session, ticker: str) -> bool:
    """True se c'era. Togliere un preferito che non c'e' non e' un errore."""
    stock = _stock(db, ticker)
    if stock is None:
        return False
    riga = db.get(Preferito, stock.id)
    if riga is not None and riga.origine == ETORO and db.get(PreferitoEscluso, stock.id) is None:
        # E' ancora nella watchlist: senza esclusione tornerebbe al giro dopo.
        db.add(PreferitoEscluso(stock_id=stock.id, escluso_il=datetime.now(UTC)))
    tolti = db.execute(delete(Preferito).where(Preferito.stock_id == stock.id)).rowcount
    db.commit()
    return bool(tolti)
