"""Economic calendar endpoint: aggregated earnings + macro events.

Single read-only GET. Auth required (consistent with the rest of /api).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.calendar import (
    CalendarOut,
    EarningsEventOut,
    MacroEventOut,
)
from app.services import calendar_service
from app.services.calendar_service import (
    EarningsEvent,
    MacroEventDC,
)

router = APIRouter(prefix="/api", tags=["calendar"])


_VALID_KINDS = {"earnings", "macro"}
_VALID_IMPORTANCE = {"high", "medium", "low"}
_MAX_RANGE_DAYS = 366


def _parse_csv(raw: str | None, valid: set[str], param_name: str) -> set[str] | None:
    """Comma-separated query param → validated set, or None for "no filter".

    Raises 422 on unknown values. Empty/missing string → None (full set).
    """
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    invalid = sorted(set(parts) - valid)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"{param_name} contains invalid values: {invalid}. Allowed: {sorted(valid)}",
        )
    return set(parts)


@router.get("/calendar", response_model=CalendarOut)
def get_calendar(
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    kinds: Annotated[str | None, Query()] = None,
    importance: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CalendarOut:
    """Aggregate calendar events.

    Query params:
      from        ISO date, default = today UTC
      to          ISO date, default = today UTC + 30 days
      kinds       comma-separated subset of {earnings, macro}, default both
      importance  comma-separated subset of {high, medium, low}; macros only

    Validation:
      - from <= to  (else 422)
      - to - from <= 366 days (else 422 — abuse cap)
      - unknown kinds / importance values → 422
    """
    today = datetime.now(UTC).date()
    if date_from is None:
        date_from = today
    if date_to is None:
        date_to = today + timedelta(days=30)

    if date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail=f"from ({date_from}) must be <= to ({date_to})",
        )
    if (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"range too wide ({(date_to - date_from).days} days); max {_MAX_RANGE_DAYS}",
        )

    kinds_set = _parse_csv(kinds, _VALID_KINDS, "kinds")
    importance_set = _parse_csv(importance, _VALID_IMPORTANCE, "importance")

    events = calendar_service.get_events(
        db,
        date_from,
        date_to,
        kinds=kinds_set,
        importance=importance_set,
    )

    out_events: list[EarningsEventOut | MacroEventOut] = []
    for e in events:
        if isinstance(e, EarningsEvent):
            out_events.append(EarningsEventOut(
                date=e.date,
                ticker=e.ticker,
                name=e.name,
                eps_estimate=e.eps_estimate,
                revenue_estimate=e.revenue_estimate,
                sector=e.sector,
                market_cap=e.market_cap,
                forward_pe=e.forward_pe,
                earnings_growth=e.earnings_growth,
                composite_score=e.composite_score,
                risk_tier=e.risk_tier,  # type: ignore[arg-type]
            ))
        elif isinstance(e, MacroEventDC):
            out_events.append(MacroEventOut(
                date=e.date,
                label=e.label,
                importance=e.importance,  # type: ignore[arg-type]
                region=e.region,  # type: ignore[arg-type]
            ))

    return CalendarOut(
        date_from=date_from,
        date_to=date_to,
        events=out_events,
    )
