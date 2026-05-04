"""POST /api/rules/preview — evaluate an expression against a single stock's OHLCV."""
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import OhlcvDaily, Stock, User
from app.rules.composite import evaluate_expression, snapshot_expression, validate_expression

router = APIRouter(prefix="/api/rules", tags=["rules"])


class PreviewRequest(BaseModel):
    ticker: str
    expression: dict[str, Any]


class PreviewResponse(BaseModel):
    matched: bool
    snapshot: dict[str, Any]


def _load_ohlcv(db: Session, stock_id: int, limit: int = 252) -> pd.DataFrame | None:
    rows = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock_id)
            .order_by(OhlcvDaily.date.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    rows = rows[-limit:]
    return pd.DataFrame({
        "open": [float(r.open) for r in rows],
        "high": [float(r.high) for r in rows],
        "low": [float(r.low) for r in rows],
        "close": [float(r.close) for r in rows],
        "volume": [int(r.volume) for r in rows],
    })


@router.post(
    "/preview",
    response_model=PreviewResponse,
    dependencies=[Depends(require_json)],
)
def preview_rule(
    payload: PreviewRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PreviewResponse:
    try:
        validate_expression(payload.expression)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # Catalog has duplicate rows for tickers in multiple indices; .first()
    # tolerates that (any matching row is fine for OHLCV preview).
    stock = db.execute(
        select(Stock).where(Stock.ticker == payload.ticker).limit(1)
    ).scalars().first()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {payload.ticker}")
    ohlcv = _load_ohlcv(db, stock.id)
    if ohlcv is None or len(ohlcv) < 2:
        return PreviewResponse(matched=False, snapshot={"error": "insufficient data"})
    try:
        matched = evaluate_expression(payload.expression, ohlcv)
        snap = snapshot_expression(payload.expression, ohlcv)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PreviewResponse(matched=matched, snapshot=snap)
