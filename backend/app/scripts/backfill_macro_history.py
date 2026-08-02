"""Full-history backfill of the MACRO STATE series the conditional screen needs.

Separate from `refresh_fred` on purpose, on two axes:

* **Purpose.** `CURATED_SERIES` is documented as "indicators the user sees on
  the calendar" — releases with a publication schedule. These are *state*
  series: they have no release event, nobody wants a calendar chip for them,
  and they exist only to condition the outcome study. Mixing them into the
  curated set would put junk on the calendar.
* **Depth.** The refresh job pulls a rolling 3 years, which is the right
  window for a UI. A 10-year no-look-ahead replay needs the whole history, and
  fetching that on every cron tick would be waste.

They still land in `macro_series` / `macro_observations` — same schema, same
upsert semantics. They stay off the calendar because that surface joins events
to series by `label` against a hardcoded event list, and these labels match
nothing; `fred_release_id=None` also means no release dates are ever fetched.

Why these three, and not "everything FRED has": each is daily, deep, and
carries information that is NOT a transform of the single stock's own price —
the property that makes it worth testing at all. Anything monthly (CPI, NFP)
is too coarse for a 5-to-63-bar horizon and would mostly measure the calendar.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_macro_history
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MacroObservation, MacroSeries
from app.services import fred_service


@dataclass(frozen=True)
class StateSeries:
    fred_series_id: str
    label: str
    region: str
    unit: str
    description: str


# Deliberately small. Every series here costs a column in the screen and
# therefore a slice of the multiple-testing budget — adding one is not free.
STATE_SERIES: tuple[StateSeries, ...] = (
    StateSeries(
        "VIXCLS", "CBOE VIX (stato, non calendario)", "US", "index",
        "CBOE Volatility Index, daily close. Implied vol of the S&P 500 — the "
        "single most-cited market-stress state variable, daily since 1990.",
    ),
    StateSeries(
        "T10Y2Y", "Curva 10y-2y (stato, non calendario)", "US", "pct",
        "10-Year minus 2-Year Treasury constant-maturity spread, computed by "
        "FRED. Negative = inverted curve. Daily since 1976.",
    ),
    # Credit stress. NOT the ICE BofA OAS series (BAMLH0A0HYM2), which is the
    # obvious first choice and is unusable here: ICE restricted the licence
    # and FRED now serves only a ~3-year rolling window for every BAML series
    # — measured, not assumed (795 obs from 2023-08, unchanged when asked for
    # an explicit 1996 start). Moody's Baa-over-10y is not ICE-licensed and
    # goes back to 1986, which is what a 10-year replay actually needs.
    StateSeries(
        "BAA10Y", "Spread Baa-10y (stato, non calendario)", "US", "pct",
        "Moody's Baa corporate yield minus the 10-Year Treasury. Credit-stress "
        "proxy: widens ahead of equity drawdowns more often than not. Daily "
        "since 1986.",
    ),
)


def _ensure_series(db: Session) -> dict[str, MacroSeries]:
    out: dict[str, MacroSeries] = {}
    for c in STATE_SERIES:
        row = db.execute(
            select(MacroSeries).where(MacroSeries.fred_series_id == c.fred_series_id)
        ).scalar_one_or_none()
        if row is None:
            row = MacroSeries(
                fred_series_id=c.fred_series_id,
                fred_release_id=None,   # never on the calendar
                label=c.label,
                region=c.region,
                importance="low",       # state, not an event to watch for
                unit=c.unit,
                description=c.description,
            )
            db.add(row)
        else:
            row.label = c.label
            row.description = c.description
            row.unit = c.unit
        out[c.fred_series_id] = row
    db.flush()
    return out


def _backfill_observations(db: Session, series: MacroSeries) -> tuple[int, int]:
    """Full history, no observation_start. Returns (inserted, updated)."""
    obs = fred_service.fetch_observations(series.fred_series_id)
    if not obs:
        logger.warning(f"[macro-backfill] {series.fred_series_id}: no observations returned")
        return (0, 0)
    existing = {
        d: rid for rid, d in db.execute(
            select(MacroObservation.id, MacroObservation.date).where(
                MacroObservation.series_id == series.id
            )
        ).all()
    }
    inserted = updated = 0
    for o in obs:
        rid = existing.get(o.date)
        if rid is None:
            db.add(MacroObservation(series_id=series.id, date=o.date, value=o.value))
            inserted += 1
        else:
            row = db.get(MacroObservation, rid)
            if row is not None and row.value != o.value:
                row.value = o.value
                updated += 1
    return (inserted, updated)


def run() -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        rows = _ensure_series(db)
        db.commit()
        total_i = total_u = 0
        for sid, series in rows.items():
            ins, upd = _backfill_observations(db, series)
            db.commit()
            total_i += ins
            total_u += upd
            span = db.execute(
                select(
                    MacroObservation.date,
                ).where(MacroObservation.series_id == series.id)
                .order_by(MacroObservation.date)
            ).scalars().all()
            if span:
                logger.info(
                    f"[macro-backfill] {sid}: +{ins} new, {upd} revised, "
                    f"now {len(span)} obs {span[0]} → {span[-1]}"
                )
            else:
                logger.warning(f"[macro-backfill] {sid}: still empty")
        print(f"\nBackfill done: {total_i} inserted, {total_u} revised.")
    finally:
        db.close()


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
