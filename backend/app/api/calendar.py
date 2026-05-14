"""Economic calendar endpoint: aggregated earnings + macro events.

Single read-only GET. Auth required (consistent with the rest of /api).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import MacroObservation, MacroReleaseDate, MacroSeries, User
from app.schemas.calendar import (
    CalendarOut,
    EarningsEventOut,
    MacroEventOut,
    MacroObservationOut,
    MacroReleaseOut,
    MacroSeriesDetailOut,
)
from app.services import calendar_service
from app.services.calendar_service import (
    EarningsEvent,
    MacroEventDC,
    currency_for_region,
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
                earnings_when=e.earnings_when,  # type: ignore[arg-type]
                eps_reported=e.eps_reported,
                surprise_pct=e.surprise_pct,
            ))
        elif isinstance(e, MacroEventDC):
            out_events.append(MacroEventOut(
                date=e.date,
                label=e.label,
                importance=e.importance,  # type: ignore[arg-type]
                region=e.region,  # type: ignore[arg-type]
                prev_value=e.prev_value,
                prev_date=e.prev_date,
                prior_value=e.prior_value,
                prior_date=e.prior_date,
                change_pct=e.change_pct,
                unit=e.unit,
                history=[
                    MacroObservationOut(date=d, value=v)
                    for d, v in e.history
                ],
                release_time=e.release_time,
                expected_value=e.expected_value,
                actual_value=e.actual_value,
                surprise_pct=e.surprise_pct,
                series_id=e.series_id,
                source=e.source,
                currency=currency_for_region(e.region),
            ))

    return CalendarOut(
        date_from=date_from,
        date_to=date_to,
        events=out_events,
    )


def _period_label(d: date) -> str:
    """Italian short-month label for a release date — "Apr", "Mag", "Set"…
    Mirrors the "(Apr)" suffix Investing.com shows in its history table.
    """
    months = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
              "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    return months[d.month - 1]


@router.get("/macro/{series_id}", response_model=MacroSeriesDetailOut)
def get_macro_detail(
    series_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MacroSeriesDetailOut:
    """Detail view for a single macro indicator — the data behind the
    /macro/:series_id frontend page (Investing-style layout).

    Returns:
      - Series metadata (label, region, currency, source, importance, unit, description)
      - Latest release (actual / expected / previous, with surprise)
      - Full release history (newest → oldest, no truncation — UI applies range filter)
      - Upcoming scheduled release dates (next ~3)

    `expected_value` on historical rows is NULL: we don't backfill consensus
    for past releases (Forexfactory's free feed only carries the current
    week's forecasts). Frontend renders "—" in that column for old rows.
    """
    series = db.get(MacroSeries, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail=f"MacroSeries {series_id} not found")

    # Full history: every observation ever stored, newest first. The
    # frontend bar chart applies range filtering (1Y / 5Y / MAX) client-
    # side — no need for a date filter param on this endpoint since the
    # row count per series is bounded (~360 monthly = 30y of history).
    obs_rows = db.execute(
        select(MacroObservation.date, MacroObservation.value)
        .where(MacroObservation.series_id == series_id)
        .order_by(MacroObservation.date.desc())
    ).all()

    # Build release history with previous_value = the observation
    # immediately before this one, so the table can show "Precedente"
    # per row without a frontend pass over the same data. obs_rows is
    # newest-first, so the previous value for row i is the value at
    # row i+1 (older).
    history: list[MacroReleaseOut] = []
    for i, row in enumerate(obs_rows):
        prev_v = obs_rows[i + 1].value if i + 1 < len(obs_rows) else None
        history.append(
            MacroReleaseOut(
                release_date=row.date,
                period_label=_period_label(row.date),
                actual_value=row.value,
                expected_value=None,  # not backfilled — see docstring
                previous_value=prev_v,
                release_time_utc=None,  # observations carry no time info
            )
        )

    latest = history[0] if history else None

    upcoming_rows = db.execute(
        select(MacroReleaseDate.date)
        .where(
            MacroReleaseDate.series_id == series_id,
            MacroReleaseDate.date > datetime.now(UTC).date(),
        )
        .order_by(MacroReleaseDate.date.asc())
        .limit(5)
    ).scalars().all()

    return MacroSeriesDetailOut(
        series_id=series.id,
        fred_series_id=series.fred_series_id,
        label=series.label,
        region=series.region,
        currency=currency_for_region(series.region),
        importance=series.importance,  # type: ignore[arg-type]
        unit=series.unit,
        description=series.description,
        source=series.source,
        last_refreshed_at=(
            series.last_refreshed_at.isoformat() if series.last_refreshed_at else None
        ),
        latest=latest,
        history=history,
        upcoming=list(upcoming_rows),
    )
