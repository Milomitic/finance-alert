"""Institutional / superinvestor portfolio endpoints.

Four routes:
- GET /api/institutionals                          (list + summaries)
- GET /api/institutionals/aggregate                (cross-portfolio rollups)
- GET /api/institutionals/{slug}                   (one portfolio detail)
- GET /api/stocks/{ticker}/institutional-holders   (sidebar card on stock page)

The 4th lives under `/api/stocks/...` for URL hygiene (it's logically a
sub-resource of the stock). It's wired here in the institutionals
router because the underlying query lives in `institutional_service`
and we want all institutional-domain code grouped.
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.institutional import (
    AggregateStatsOut,
    HoldingDetailOut,
    InstitutionalDetailOut,
    InstitutionalSummaryOut,
    TickerHolderOut,
    TickerHoldersOut,
)
from app.services import institutional_service

router = APIRouter(prefix="/api", tags=["institutionals"])


@router.get(
    "/institutionals",
    response_model=list[InstitutionalSummaryOut],
)
def list_institutionals(
    type: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[InstitutionalSummaryOut]:
    rows = institutional_service.list_institutionals(
        db, type_=type, source=source, limit=limit
    )
    return [InstitutionalSummaryOut.model_validate(r) for r in rows]


@router.get(
    "/institutionals/aggregate",
    response_model=AggregateStatsOut,
)
def aggregate(
    type: Annotated[str | None, Query()] = None,
    most_picked_limit: int = 25,
    recent_actions_limit: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AggregateStatsOut:
    """Cross-portfolio overview: most-picked tickers, recent buys/sells,
    sector tilt. Computed only on each fund's LATEST filing.

    Note: `/aggregate` is declared BEFORE `/{slug}` so FastAPI's path
    routing doesn't capture "aggregate" as a slug.
    """
    stats = institutional_service.get_aggregate_stats(
        db,
        type_=type,
        most_picked_limit=most_picked_limit,
        recent_actions_limit=recent_actions_limit,
    )
    return AggregateStatsOut.model_validate(stats)


@router.get(
    "/institutionals/{slug}",
    response_model=InstitutionalDetailOut,
)
def get_detail(
    slug: str,
    period_end: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> InstitutionalDetailOut:
    detail = institutional_service.get_institutional_detail(
        db, slug, period_end=period_end
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Institutional not found")
    return InstitutionalDetailOut(
        institutional=InstitutionalSummaryOut.model_validate(detail.institutional),
        holdings=[HoldingDetailOut.model_validate(h) for h in detail.holdings],
        filed_date=detail.filed_date,
        available_periods=detail.available_periods,
    )


@router.get(
    "/stocks/{ticker}/institutional-holders",
    response_model=TickerHoldersOut,
    tags=["stocks"],
)
def get_ticker_holders(
    ticker: str,
    limit: int = 25,
    include_historical: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TickerHoldersOut:
    """Used by the stock detail card. Returns the list of
    institutionals/superinvestors holding `ticker` in their latest
    filing. Empty list = no tracked fund holds it (still a 200,
    not a 404).

    With `include_historical=true` the response also carries a
    `historical` list: funds that held the ticker in the past but are
    no longer current holders (sold out or stale), each with their
    most recent holding — used by the dual-encoded infographic to show
    past conviction alongside live positions."""
    holders = institutional_service.holders_for_ticker(db, ticker, limit=limit)
    historical: list[TickerHolderOut] = []
    if include_historical:
        current_ids = {h.institutional_id for h in holders}
        hist = institutional_service.historical_holders_for_ticker(
            db, ticker, limit=limit, exclude_ids=current_ids
        )
        historical = [TickerHolderOut.model_validate(h) for h in hist]
    return TickerHoldersOut(
        ticker=ticker,
        holders=[TickerHolderOut.model_validate(h) for h in holders],
        historical=historical,
    )
