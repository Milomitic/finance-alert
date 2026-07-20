"""CRUD for per-stock chart drawings (horizontal levels + trend lines)."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import StockDrawing


def list_for_stock(db: Session, stock_id: int) -> list[StockDrawing]:
    return list(
        db.execute(
            select(StockDrawing)
            .where(StockDrawing.stock_id == stock_id)
            .order_by(StockDrawing.created_at.asc())
        ).scalars()
    )


def create_horizontal(db: Session, stock_id: int, *, price: float) -> StockDrawing:
    d = StockDrawing(stock_id=stock_id, kind="horizontal", price=price)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def create_trend(
    db: Session, stock_id: int, *, x1: int, y1: float, x2: int, y2: float
) -> StockDrawing:
    d = StockDrawing(stock_id=stock_id, kind="trend", x1=x1, y1=y1, x2=x2, y2=y2)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def delete_one(db: Session, stock_id: int, drawing_id: int) -> None:
    """Delete a single drawing. Scoped to `stock_id` so a stale id from
    another stock can't delete across tickers. Raises LookupError when the
    (stock, id) pair doesn't exist."""
    d = db.execute(
        select(StockDrawing).where(
            StockDrawing.id == drawing_id, StockDrawing.stock_id == stock_id
        )
    ).scalar_one_or_none()
    if d is None:
        raise LookupError("drawing not found")
    db.delete(d)
    db.commit()


def clear_for_stock(db: Session, stock_id: int) -> int:
    """Delete every drawing for a stock. Returns the number removed."""
    result = db.execute(
        delete(StockDrawing).where(StockDrawing.stock_id == stock_id)
    )
    db.commit()
    return result.rowcount or 0
