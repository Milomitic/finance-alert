"""Per-stock chart drawings CRUD (horizontal levels + trend lines).

Replaces the old localStorage-only store so drawings survive a browser wipe
and sync across devices on the cloud deployment.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import Stock, User
from app.schemas.stock_drawing import (
    DrawingCreate,
    DrawingCreated,
    HorizontalOut,
    StockDrawingsOut,
    TrendOut,
)
from app.services import stock_drawing_service

router = APIRouter(tags=["stock-drawings"])


def _stock_id_or_404(db: Session, ticker: str) -> int:
    # Read path tolerates any residual dup with limit(1) (see CLAUDE.md dedup
    # note): scalar_one_or_none would raise MultipleResultsFound.
    s = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if s is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
    return s.id


@router.get("/api/stocks/{ticker}/drawings", response_model=StockDrawingsOut)
def list_drawings(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockDrawingsOut:
    stock_id = _stock_id_or_404(db, ticker)
    rows = stock_drawing_service.list_for_stock(db, stock_id)
    horizontal = [
        HorizontalOut(id=r.id, price=r.price)
        for r in rows
        if r.kind == "horizontal" and r.price is not None
    ]
    trend = [
        TrendOut(id=r.id, x1=r.x1, y1=r.y1, x2=r.x2, y2=r.y2)
        for r in rows
        if r.kind == "trend" and None not in (r.x1, r.y1, r.x2, r.y2)
    ]
    return StockDrawingsOut(horizontal=horizontal, trend=trend)


@router.post(
    "/api/stocks/{ticker}/drawings",
    response_model=DrawingCreated,
    status_code=201,
    dependencies=[Depends(require_json)],
)
def create_drawing(
    ticker: str,
    body: DrawingCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DrawingCreated:
    stock_id = _stock_id_or_404(db, ticker)
    if body.kind == "horizontal":
        d = stock_drawing_service.create_horizontal(db, stock_id, price=body.price)
    else:
        d = stock_drawing_service.create_trend(
            db, stock_id, x1=body.x1, y1=body.y1, x2=body.x2, y2=body.y2
        )
    return DrawingCreated(id=d.id, kind=d.kind)


@router.delete(
    "/api/stocks/{ticker}/drawings/{drawing_id}",
    status_code=204,
    dependencies=[Depends(require_json)],
)
def delete_drawing(
    ticker: str,
    drawing_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    stock_id = _stock_id_or_404(db, ticker)
    try:
        stock_drawing_service.delete_one(db, stock_id, drawing_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Drawing not found") from None


@router.delete(
    "/api/stocks/{ticker}/drawings",
    status_code=204,
    dependencies=[Depends(require_json)],
)
def clear_drawings(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    stock_id = _stock_id_or_404(db, ticker)
    stock_drawing_service.clear_for_stock(db, stock_id)
