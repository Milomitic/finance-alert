"""Macro-event series + observations sourced from FRED.

Why two tables
--------------
- `MacroSeries` is a stable catalog row per economic indicator we
  surface in the calendar (CPI, NFP, FOMC, ECB rate, …). One row per
  series, holding the FRED `series_id` + `release_id` + the
  user-facing label/region/importance.
- `MacroObservation` holds the historical time series — many rows per
  series. The calendar's "show me prev value + change vs prior"
  feature reads from here.

The calendar's "next FOMC = 2026-06-18" and "previous CPI was 3.2%
YoY" come from the same DB, refreshed once per day by
`scripts/refresh_fred.py`.

When `FRED_API_KEY` is unset (or FRED is unreachable), neither table
gets populated and the calendar falls back to the hardcoded list in
`services/calendar_macros.py`.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MacroSeries(Base):
    """One row per economic indicator we follow.

    `fred_series_id`: e.g. "CPIAUCSL" (US CPI all items),
    "PAYEMS" (NFP, total non-farm payrolls), "DGS10" (10y Treasury
    yield). Used for time-series fetch.

    `fred_release_id`: integer for `release/dates` calls — gives the
    publication schedule. e.g. 10 = "Consumer Price Index", 50 =
    "Employment Situation", 101 = FOMC. May be null when we only
    care about historical values, not the release schedule.
    """
    __tablename__ = "macro_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fred_series_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    fred_release_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    importance: Mapped[str] = mapped_column(String(16), nullable=False)  # high|medium|low
    # How to display the value in the UI (pct / level / index / yield).
    # The calendar's insight panel formats numbers based on this.
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Optional Italian description shown in the tooltip / detail card.
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Publishing organization, surfaced in the macro detail page header
    # ("Fonte: U.S. Bureau of Labor Statistics"). Italian-friendly free
    # text — populated by `scripts/seed_macro_sources.py` for known
    # FRED series (CPI/NFP/FOMC/...) using a small static map. Older rows
    # may be NULL until the seed runs.
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MacroObservation(Base):
    """Historical observations for a `MacroSeries`. One row per (series,
    date). `value` is NULL when FRED reports "." (no data for that
    period — e.g. revisions or hold-out months).
    """
    __tablename__ = "macro_observations"
    __table_args__ = (
        UniqueConstraint("series_id", "date", name="uq_macro_obs_series_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("macro_series.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)


class MacroReleaseDate(Base):
    """Scheduled publication date for a `MacroSeries` (sourced from
    `release/dates`). Used by the calendar to render "next CPI:
    2026-06-10" rows. Many rows per series — past + future.
    """
    __tablename__ = "macro_release_dates"
    __table_args__ = (
        UniqueConstraint("series_id", "date", name="uq_macro_rel_series_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("macro_series.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
