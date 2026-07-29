"""Setups API — what is FORMING, ahead of the signal.

Note what this payload deliberately does NOT contain: a probability. Setups
carry `convenience`, an attention/ordering score, and the response says so in
its field docs so a future consumer can't mistake one for the other.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Stock, StockSetup, User
from app.models.stock_setup import STATUS_ACTIVE
from app.services import setup_service

router = APIRouter(prefix="/api/setups", tags=["setups"])


class SetupOut(BaseModel):
    id: int
    ticker: str
    name: str | None = None
    detector: str
    tone: str
    #: 0..1 — share of the detector's gate chain already satisfied.
    proximity: float
    #: 0..100 ATTENTION score for ordering. NOT a probability: setups make no
    #: forecast, and nothing in the engine's calibration applies to them.
    convenience: float
    #: What still has to happen for the signal to fire — the actionable part.
    missing: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    annotations: dict | None = None


class SetupListOut(BaseModel):
    setups: list[SetupOut]
    #: The feature's own report card: does it convert, and with how much
    #: warning. `conversion_rate`/`avg_lead_days` are null until something
    #: resolves — null means "not known yet", not "zero".
    stats: dict


@router.get("", response_model=SetupListOut)
def list_setups(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    tone: str | None = None,
    ticker: str | None = None,
) -> SetupListOut:
    q = (
        select(StockSetup, Stock)
        .join(Stock, Stock.id == StockSetup.stock_id)
        .where(StockSetup.status == STATUS_ACTIVE)
    )
    if tone in ("bull", "bear"):
        q = q.where(StockSetup.tone == tone)
    if ticker:
        # Per-stock view (the detail page). Deliberately NOT limited to the
        # shortlist: on a page about ONE stock, "this setup exists but ranks
        # 14th market-wide" is still worth seeing. The global list is the one
        # that has to stay short to be usable.
        q = q.where(Stock.ticker == ticker.upper())
    else:
        # Rows outside their detector's top N still exist — they keep their
        # history so `lead_days` stays honest — but are not what the user is
        # asked to scan.
        q = q.where(StockSetup.shortlisted.is_(True))
    q = q.order_by(StockSetup.convenience.desc()).limit(limit)

    out: list[SetupOut] = []
    for row, stock in db.execute(q).all():
        try:
            ann = json.loads(row.annotations_json) if row.annotations_json else None
        except (ValueError, TypeError):
            ann = None
        out.append(
            SetupOut(
                id=row.id, ticker=stock.ticker, name=stock.name,
                detector=row.detector, tone=row.tone,
                proximity=row.proximity, convenience=row.convenience,
                missing=row.missing,
                first_seen_at=row.first_seen_at.isoformat() if row.first_seen_at else None,
                last_seen_at=row.last_seen_at.isoformat() if row.last_seen_at else None,
                annotations=ann,
            )
        )
    return SetupListOut(setups=out, stats=setup_service.conversion_stats(db))
