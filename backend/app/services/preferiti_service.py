"""La lista dei titoli preferiti (FA-112): leggerla, aggiungere, togliere."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Stock
from app.models.preferito import Preferito


def _stock(db: Session, ticker: str) -> Stock | None:
    # `.limit(1)`: la forma difensiva del CLAUDE.md contro i doppioni storici.
    return db.execute(select(Stock).where(Stock.ticker == ticker).limit(1)).scalars().first()


def elenco(db: Session) -> list[tuple[Stock, datetime]]:
    """Nell'ordine in cui sono stati aggiunti: la lista resta ferma, e un
    titolo nuovo va in fondo invece di spostare tutti gli altri."""
    righe = db.execute(
        select(Stock, Preferito.aggiunto_il)
        .join(Preferito, Preferito.stock_id == Stock.id)
        .order_by(Preferito.aggiunto_il, Stock.ticker)
    ).all()
    return [(s, a) for s, a in righe]


def stock_ids(db: Session) -> set[int]:
    """Gli id dei preferiti, per chi ordina o filtra per rilevanza (FA-113)."""
    return set(db.execute(select(Preferito.stock_id)).scalars())


def aggiungi(db: Session, ticker: str) -> tuple[Stock, datetime] | None:
    """Idempotente. None se il ticker non e' nel catalogo."""
    stock = _stock(db, ticker)
    if stock is None:
        return None
    riga = db.get(Preferito, stock.id)
    if riga is None:
        riga = Preferito(stock_id=stock.id, aggiunto_il=datetime.now(UTC))
        db.add(riga)
        db.commit()
    return stock, riga.aggiunto_il


def togli(db: Session, ticker: str) -> bool:
    """True se c'era. Togliere un preferito che non c'e' non e' un errore."""
    stock = _stock(db, ticker)
    if stock is None:
        return False
    tolti = db.execute(delete(Preferito).where(Preferito.stock_id == stock.id)).rowcount
    db.commit()
    return bool(tolti)
