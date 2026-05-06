"""Refresh FRED-driven macro calendar.

Two phases:
  1. **Bootstrap**: ensure each `CURATED_SERIES` row exists in
     `macro_series`. Idempotent — run any number of times, only the
     first one inserts.
  2. **Refresh**: for each series, fetch (a) the publication-date
     schedule via `release/dates`, (b) the historical observations
     via `series/observations`, and UPSERT into `macro_release_dates`
     + `macro_observations`. Sets `MacroSeries.last_refreshed_at`.

Designed to be called once a day (manual or via APScheduler). The
calendar API reads from these tables, so a stale refresh just shows
older data — no errors, no missing rows.

Usage (manual):
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.refresh_fred
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import MacroObservation, MacroReleaseDate, MacroSeries
from app.services import fred_service

Importance = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class CuratedSeries:
    fred_series_id: str
    fred_release_id: int | None
    label: str
    region: str
    importance: Importance
    unit: str | None  # "pct" | "level" | "index" | "yield" | None
    description: str | None = None


# Curated set of FRED series. Each row defines one indicator the user
# sees on the calendar. Adding a new series:
#   1. Find the FRED series_id (https://fred.stlouisfed.org → search)
#   2. Find the release_id (search → click release link → URL contains it)
#   3. Add a row here.
#
# Region codes match `services/calendar_macros.Region`. The release_id
# can be null when the series doesn't have a clean publication
# schedule (e.g. derived series with no fixed cadence) — the calendar
# will then only show its history, not future events.
CURATED_SERIES: tuple[CuratedSeries, ...] = (
    # ── US ──────────────────────────────────────────────────────────
    CuratedSeries("CPIAUCSL", 10,  "US CPI release",                "US", "high",   "index", "Consumer Price Index All Urban Consumers"),
    CuratedSeries("PPIACO",   46,  "US PPI release",                "US", "medium", "index", "Producer Price Index All Commodities"),
    CuratedSeries("PAYEMS",   50,  "US NFP / Non-Farm Payrolls",    "US", "high",   "level", "Total Non-Farm Payrolls (thousands)"),
    CuratedSeries("UNRATE",   50,  "US Unemployment Rate",          "US", "medium", "pct",   "Civilian Unemployment Rate"),
    CuratedSeries("FEDFUNDS", 101, "FOMC rate decision",            "US", "high",   "pct",   "Effective Federal Funds Rate"),
    CuratedSeries("GDPC1",    53,  "US GDP (real)",                 "US", "high",   "level", "Real GDP, chained 2017 dollars"),
    CuratedSeries("RSAFS",    9,   "US Retail Sales",               "US", "medium", "level", "Retail Sales (Advance)"),
    CuratedSeries("DGS10",    None, "US 10y Treasury yield",        "US", "low",    "pct",   "10-Year Treasury Constant Maturity Rate"),
    CuratedSeries("DGS2",     None, "US 2y Treasury yield",         "US", "low",    "pct",   "2-Year Treasury Constant Maturity Rate"),
    # ── Eurozone / EU ──────────────────────────────────────────────
    CuratedSeries("CP0000EZ19M086NEST", 178, "Eurozone HICP flash", "EZ", "high",   "index", "Harmonised CPI, Euro Area 19 countries"),
    # FRED's ECB rate series (ECBDFR) and BoE / BoJ aren't on a clean
    # release calendar via release/dates — they're updated when the
    # central bank publishes. We track the series for history; release
    # schedule comes from the hardcoded fallback.
    CuratedSeries("ECBDFR",   None, "ECB Deposit Facility Rate",    "EU", "high",   "pct",   "ECB main deposit facility rate"),
    # ── UK ─────────────────────────────────────────────────────────
    CuratedSeries("IUDSOIA",  None, "BoE Bank Rate",                "UK", "high",   "pct",   "Bank of England Bank Rate"),
    # ── Japan ──────────────────────────────────────────────────────
    CuratedSeries("INTDSRJPM193N", None, "BoJ policy rate",         "JP", "medium", "pct",   "Discount rate (Bank of Japan)"),
)


def _ensure_series(db: Session) -> dict[str, MacroSeries]:
    """Idempotently insert/update each `CURATED_SERIES` row into
    `macro_series`. Returns a map fred_series_id → ORM row."""
    out: dict[str, MacroSeries] = {}
    for c in CURATED_SERIES:
        row = db.execute(
            select(MacroSeries).where(MacroSeries.fred_series_id == c.fred_series_id)
        ).scalar_one_or_none()
        if row is None:
            row = MacroSeries(
                fred_series_id=c.fred_series_id,
                fred_release_id=c.fred_release_id,
                label=c.label,
                region=c.region,
                importance=c.importance,
                unit=c.unit,
                description=c.description,
            )
            db.add(row)
        else:
            # Refresh metadata in case the curated map changed
            row.fred_release_id = c.fred_release_id
            row.label = c.label
            row.region = c.region
            row.importance = c.importance
            row.unit = c.unit
            row.description = c.description
        out[c.fred_series_id] = row
    db.flush()
    return out


def _refresh_observations(db: Session, series: MacroSeries) -> int:
    """Fetch the last ~3 years of observations for `series` from FRED
    and UPSERT into `macro_observations`. Returns rows touched."""
    start = date.today() - timedelta(days=3 * 365)
    obs = fred_service.fetch_observations(
        series.fred_series_id, observation_start=start
    )
    if not obs:
        return 0
    # Bulk-fetch existing dates so we only INSERT new rows.
    existing_dates = set(
        db.execute(
            select(MacroObservation.date).where(
                MacroObservation.series_id == series.id
            )
        ).scalars()
    )
    inserted = 0
    for o in obs:
        if o.date in existing_dates:
            # Update the value in case FRED revised it.
            row = db.execute(
                select(MacroObservation).where(
                    MacroObservation.series_id == series.id,
                    MacroObservation.date == o.date,
                )
            ).scalar_one()
            row.value = o.value
        else:
            db.add(
                MacroObservation(
                    series_id=series.id, date=o.date, value=o.value
                )
            )
            inserted += 1
    return inserted


def _refresh_release_dates(db: Session, series: MacroSeries) -> int:
    """Fetch upcoming + recent publication dates for `series` from FRED
    and UPSERT into `macro_release_dates`. Returns rows inserted."""
    if series.fred_release_id is None:
        return 0
    # Realtime window: 1y back + 6mo forward. FRED publishes future
    # scheduled dates when the issuing agency announces them.
    start = date.today() - timedelta(days=365)
    end = date.today() + timedelta(days=180)
    dates = fred_service.fetch_release_dates(
        series.fred_release_id,
        realtime_start=start,
        realtime_end=end,
    )
    if not dates:
        return 0
    existing = set(
        db.execute(
            select(MacroReleaseDate.date).where(
                MacroReleaseDate.series_id == series.id
            )
        ).scalars()
    )
    inserted = 0
    for d in dates:
        if d.date in existing:
            continue
        db.add(MacroReleaseDate(series_id=series.id, date=d.date))
        inserted += 1
    return inserted


def run() -> None:
    if not fred_service._is_enabled():
        logger.warning(
            "[fred] FRED_API_KEY not configured — skipping refresh"
        )
        return
    db = SessionLocal()
    try:
        series_map = _ensure_series(db)
        total_obs = 0
        total_dates = 0
        for fred_id, series in series_map.items():
            n_obs = _refresh_observations(db, series)
            n_rel = _refresh_release_dates(db, series)
            series.last_refreshed_at = datetime.now(UTC)
            total_obs += n_obs
            total_dates += n_rel
            logger.info(
                f"[fred] {fred_id}: +{n_obs} obs, +{n_rel} release dates"
            )
        db.commit()
        logger.info(
            f"FRED refresh complete: {len(series_map)} series, "
            f"+{total_obs} observations, +{total_dates} release dates"
        )
    finally:
        db.close()


if __name__ == "__main__":
    run()
