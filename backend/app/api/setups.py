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
from app.models.stock_setup import STATUS_ACTIVE, STATUS_CONVERTED, STATUS_EXPIRED
from app.services import setup_service

router = APIRouter(prefix="/api/setups", tags=["setups"])


class SetupOut(BaseModel):
    id: int
    ticker: str
    name: str | None = None
    detector: str
    tone: str
    #: 0..1 — share of the detector's gate chain already satisfied. A property
    #: of the DETECTOR: every setup of the same detector at the same stage
    #: carries the same value, so it cannot rank two of them against each other.
    proximity: float
    #: Distance from price to the trigger level, in ATR units — the per-SETUP
    #: counterpart to `proximity`. Near 0 means a normal day's move would fire
    #: it. Null when the trigger is not a price crossing (squeeze_expansion
    #: waits on volatility) or when the row predates the field.
    distance_atr: float | None = None
    #: 0..100 ATTENTION score for ordering. NOT a probability: setups make no
    #: forecast, and nothing in the engine's calibration applies to them.
    convenience: float
    #: What still has to happen for the signal to fire — the actionable part.
    missing: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    annotations: dict | None = None
    #: The measured 0..1 factors behind the setup. Stored since day one and
    #: never surfaced — the detail panel shows them so the wait can be read as
    #: evidence rather than as an assertion.
    factors: dict[str, float] | None = None
    #: "active" | "converted" | "expired". Closed setups are kept, never
    #: deleted: an expired one is half of the conversion rate, and dropping
    #: them would leave only the successes on record.
    status: str = "active"
    resolved_at: str | None = None
    #: Days between first sighting and the signal firing — the warning this
    #: setup actually gave. Only set on converted rows.
    lead_days: int | None = None
    converted_alert_id: int | None = None


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
    status: str = Query(
        STATUS_ACTIVE,
        pattern="^(active|converted|expired|closed|all)$",
        description="active (default), converted, expired, closed (both), or all.",
    ),
) -> SetupListOut:
    q = (
        select(StockSetup, Stock)
        .join(Stock, Stock.id == StockSetup.stock_id)
    )
    # A setup that resolved is the only record of whether the feature works —
    # the conversion rate and the lead time both come from these rows — and
    # until now nothing could ask for them.
    if status == "closed":
        q = q.where(StockSetup.status.in_((STATUS_CONVERTED, STATUS_EXPIRED)))
    elif status != "all":
        q = q.where(StockSetup.status == status)
    if tone in ("bull", "bear"):
        q = q.where(StockSetup.tone == tone)
    if ticker:
        # Per-stock view (the detail page). Deliberately NOT limited to the
        # shortlist: on a page about ONE stock, "this setup exists but ranks
        # 14th market-wide" is still worth seeing. The global list is the one
        # that has to stay short to be usable.
        q = q.where(Stock.ticker == ticker.upper())
    elif status == STATUS_ACTIVE:
        # Rows outside their detector's top N still exist — they keep their
        # history so `lead_days` stays honest — but are not what the user is
        # asked to scan. The shortlist ranks LIVE candidates, so it is not
        # applied to closed rows: there the question is what happened, not
        # what deserves attention now.
        q = q.where(StockSetup.shortlisted.is_(True))

    if status == STATUS_ACTIVE:
        q = q.order_by(StockSetup.convenience.desc())
    else:
        # Most recently resolved first: the outcome view is a history.
        q = q.order_by(StockSetup.resolved_at.desc().nullslast())
    q = q.limit(limit)

    out: list[SetupOut] = []
    for row, stock in db.execute(q).all():
        try:
            ann = json.loads(row.annotations_json) if row.annotations_json else None
        except (ValueError, TypeError):
            ann = None
        try:
            fac = json.loads(row.factors_json) if row.factors_json else None
        except (ValueError, TypeError):
            fac = None
        out.append(
            SetupOut(
                id=row.id, ticker=stock.ticker, name=stock.name,
                detector=row.detector, tone=row.tone,
                proximity=row.proximity, distance_atr=row.distance_atr,
                convenience=row.convenience,
                missing=row.missing,
                first_seen_at=row.first_seen_at.isoformat() if row.first_seen_at else None,
                last_seen_at=row.last_seen_at.isoformat() if row.last_seen_at else None,
                annotations=ann, factors=fac,
                status=row.status,
                resolved_at=row.resolved_at.isoformat() if row.resolved_at else None,
                lead_days=row.lead_days,
                converted_alert_id=row.converted_alert_id,
            )
        )
    return SetupListOut(setups=out, stats=setup_service.conversion_stats(db))
