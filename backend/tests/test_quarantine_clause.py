"""The quarantine rule exists twice — in Python and in SQL — so it is tested
for agreement.

Two copies of a rule in two languages is exactly the shape that drifts, and
the reason there is a SQL copy at all is that the Python one only ever guarded
the OHLCV fetch plan. Measured on 2026-08-26: five genuinely dead symbols (BK,
CTRA, APLS, TERN, VSCO, no-data streaks of 129 to 262) were still being asked
for by the live-quote universe sweep every half hour, because that sweep
selects tickers in the database and knew nothing about the quarantine.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Stock
from app.services.ohlcv_service import (
    QUARANTINE_STREAK,
    REPROBE_DAYS,
    not_quarantined_clause,
    split_quarantined,
)

TODAY = date(2026, 8, 26)


def _stock(db, ticker, streak, last_nodata):
    s = Stock(
        ticker=ticker, exchange="NASDAQ", name=ticker, country="US",
        ohlcv_nodata_streak=streak, ohlcv_last_nodata_at=last_nodata,
    )
    db.add(s)
    db.commit()
    return s


CASES = [
    # (name, streak, days_since_last_nodata, expected_quarantined)
    ("dead_recent",      QUARANTINE_STREAK, 0, True),
    ("dead_yesterday",   262, 1, True),
    ("dead_but_stale",   262, REPROBE_DAYS, False),      # re-probe window elapsed
    ("dead_long_stale",  262, REPROBE_DAYS + 5, False),
    ("below_threshold",  QUARANTINE_STREAK - 1, 0, False),
    ("never_failed",     0, None, False),
    ("streak_no_date",   99, None, False),               # streak without a date
]


@pytest.mark.parametrize("name,streak,days,expected", CASES)
def test_sql_and_python_agree(db, name, streak, days, expected):
    last = None if days is None else TODAY - timedelta(days=days)
    s = _stock(db, name.upper(), streak, last)

    _, quarantined_py = split_quarantined([s], today=TODAY)
    py_says = bool(quarantined_py)

    rows = db.execute(
        select(Stock.ticker).where(not_quarantined_clause(TODAY))
    ).scalars().all()
    sql_says = s.ticker not in rows

    assert py_says == expected, f"{name}: python said {py_says}"
    assert sql_says == expected, f"{name}: sql said {sql_says}"


def test_the_five_real_dead_tickers_are_excluded(db):
    """The exact production state that prompted this: streaks well past the
    threshold, failing again today."""
    for t, streak in [("BK", 262), ("CTRA", 214), ("APLS", 188), ("TERN", 188), ("VSCO", 129)]:
        _stock(db, t, streak, TODAY)
    _stock(db, "AAPL", 0, None)

    kept = db.execute(select(Stock.ticker).where(not_quarantined_clause(TODAY))).scalars().all()
    assert kept == ["AAPL"]


def test_a_live_name_with_a_transient_miss_is_kept(db):
    """EQR, EA, AVB and CPRX also appeared in the delisted warnings, on the
    5-day path, with streak 0 — live companies hitting a transient Yahoo
    failure. Excluding those would silently drop real data, which is worse
    than the noise it would remove."""
    _stock(db, "EQR", 0, TODAY)
    kept = db.execute(select(Stock.ticker).where(not_quarantined_clause(TODAY))).scalars().all()
    assert "EQR" in kept
