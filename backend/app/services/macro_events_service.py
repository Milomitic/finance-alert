"""Macro events sourced from FRED + insights enrichment.

Pulls publication dates from `macro_release_dates` (one row per
scheduled FRED release) and joins with the series' historical
observations to enrich each event with:

  - `prev_value`: most-recent observation strictly BEFORE the
    release date — what the indicator showed last time.
  - `prior_value`: the observation before that — for computing the
    change vs prior period.
  - `change_pct`: (prev_value - prior_value) / prior_value * 100,
    or None when either is missing or zero. Surfaced on the calendar
    chip as the "trend so far" hint.
  - `history`: a small array of (date, value) for the last ~12
    observations so the calendar detail can render a sparkline.

Falls back to `calendar_macros._MACRO_EVENTS` when FRED tables are
empty or for regions FRED doesn't cover well (BoE, BoJ, KR/CN/HK
indicators we surface from the hardcoded list).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MacroObservation, MacroReleaseDate, MacroSeries


@dataclass
class MacroEventEnriched:
    """A macro event with optional insight fields populated from
    `macro_observations`. Hardcoded events leave insight fields None."""
    date: date
    label: str
    importance: str
    region: str
    # Insight fields — None for hardcoded events or when history is
    # too short to compute the comparison.
    prev_value: float | None = None
    prev_date: date | None = None        # date of `prev_value`'s observation
    prior_value: float | None = None
    prior_date: date | None = None       # date of `prior_value`'s observation
    change_pct: float | None = None
    unit: str | None = None
    series_id: int | None = None
    history: list[tuple[date, float | None]] = field(default_factory=list)
    release_time: str | None = None  # UTC HH:MM, hardcoded per-label


def _latest_value_before(
    db: Session, series_id: int, ref_date: date
) -> tuple[float | None, date | None]:
    """Return (value, observation_date) of the latest observation
    strictly before `ref_date` for `series_id`. None,None if no
    observation exists before that point."""
    row = db.execute(
        select(MacroObservation.value, MacroObservation.date)
        .where(
            MacroObservation.series_id == series_id,
            MacroObservation.date < ref_date,
        )
        .order_by(MacroObservation.date.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    return row.value, row.date


def _value_before_date(
    db: Session, series_id: int, before_date: date
) -> tuple[float | None, date | None]:
    """Helper: latest (value, date) strictly before `before_date`.
    Returns (None, None) if no such row. Used to find the
    `prior_value` given a `prev_value`'s observation date."""
    row = db.execute(
        select(MacroObservation.value, MacroObservation.date)
        .where(
            MacroObservation.series_id == series_id,
            MacroObservation.date < before_date,
        )
        .order_by(MacroObservation.date.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    return row.value, row.date


def _recent_history(
    db: Session, series_id: int, n: int = 12
) -> list[tuple[date, float | None]]:
    """Return the last `n` observations for `series_id`, ascending."""
    rows = db.execute(
        select(MacroObservation.date, MacroObservation.value)
        .where(MacroObservation.series_id == series_id)
        .order_by(MacroObservation.date.desc())
        .limit(n)
    ).all()
    # Reverse to ascending so the sparkline reads left-to-right.
    return [(r.date, r.value) for r in reversed(rows)]


def get_fred_events(
    db: Session, date_from: date, date_to: date
) -> list[MacroEventEnriched]:
    """Pull all FRED-driven release events in the window, enriched
    with prev/prior/change_pct/history. Returns [] if FRED tables
    are empty (key not configured / refresh never ran)."""
    rows = db.execute(
        select(MacroReleaseDate.date, MacroSeries)
        .join(MacroSeries, MacroSeries.id == MacroReleaseDate.series_id)
        .where(
            MacroReleaseDate.date >= date_from,
            MacroReleaseDate.date <= date_to,
        )
        .order_by(MacroReleaseDate.date.asc())
    ).all()
    out: list[MacroEventEnriched] = []
    for release_date, series in rows:
        prev_v, prev_d = _latest_value_before(db, series.id, release_date)
        prior_v: float | None = None
        prior_d: date | None = None
        change_pct: float | None = None
        if prev_v is not None and prev_d is not None:
            prior_v, prior_d = _value_before_date(db, series.id, prev_d)
            if (
                prior_v is not None
                and prior_v != 0
                and prev_v is not None
            ):
                change_pct = (prev_v - prior_v) / abs(prior_v) * 100.0
        # Extended history window: 36 observations (~3y monthly /
        # ~9mo weekly / ~36w daily). The compact sparkline takes the
        # last 12 of these; the expandable detail chart uses the full
        # set so the user can see longer trends without a second
        # roundtrip.
        out.append(
            MacroEventEnriched(
                date=release_date,
                label=series.label,
                importance=series.importance,
                region=series.region,
                prev_value=prev_v,
                prev_date=prev_d,
                prior_value=prior_v,
                prior_date=prior_d,
                change_pct=change_pct,
                unit=series.unit,
                series_id=series.id,
                history=_recent_history(db, series.id, n=36),
            )
        )
    return out
