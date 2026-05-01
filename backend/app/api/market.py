"""GET /api/dashboard/market-summary — serves the latest pre-computed snapshot."""
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.market import MarketSummaryOut
from app.services import market_stats_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

STALE_THRESHOLD = timedelta(hours=24)


@router.get("/market-summary", response_model=MarketSummaryOut, response_model_by_alias=True)
def get_market_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MarketSummaryOut:
    snap = market_stats_service.get_latest_snapshot(db)
    if snap is None:
        return MarketSummaryOut(available=False, reason="no_scan_yet")

    payload = json.loads(snap.payload)
    computed_at_utc = snap.computed_at.replace(tzinfo=UTC) if snap.computed_at.tzinfo is None else snap.computed_at
    is_stale = (datetime.now(UTC) - computed_at_utc) > STALE_THRESHOLD

    return MarketSummaryOut(
        available=True,
        is_stale=is_stale,
        computed_at=snap.computed_at,
        scan_run_id=snap.scan_run_id,
        **{"global": payload["global"]},
        by_index=payload["by_index"],
        rsi_distribution=payload["rsi_distribution"],
        sectors=payload["sectors"],
        movers=payload["movers"],
        treemap=payload["treemap"],
    )
