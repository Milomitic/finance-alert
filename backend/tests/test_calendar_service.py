"""Tests for the calendar aggregator (`app.services.calendar_service`).

We stub the fundamentals cache directly (no monkeypatched yfinance roundtrip)
because the aggregator reads `_CACHE` as a contract — that's what makes the
calendar fast and offline-safe.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Stock, StockScore
from app.services import calendar_macros, calendar_service, stock_fundamentals_service
from app.services.calendar_service import EarningsEvent, MacroEventDC
from app.services.stock_fundamentals_service import EarningsPoint, Fundamentals

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_fundamentals_cache():
    """Each test starts with an empty fundamentals cache so cache state from
    a different test (or the repo's prior runs) can't leak in."""
    stock_fundamentals_service._CACHE.clear()
    yield
    stock_fundamentals_service._CACHE.clear()


def _seed_stock_with_score(db: Session, *, ticker: str, name: str, sector: str | None = None,
                            market_cap: int | None = None, composite: float = 70.0) -> Stock:
    s = Stock(ticker=ticker, exchange="NMS", name=name, sector=sector, market_cap=market_cap)
    db.add(s)
    db.flush()
    db.add(StockScore(
        stock_id=s.id, composite=composite,
        quality=50.0, growth=50.0, value=50.0, momentum=50.0, sentiment=50.0,
        risk_tier="moderate",
        computed_at=datetime.now(UTC),
        breakdown=json.dumps({}),
    ))
    db.commit()
    return s


def _put_in_cache(ticker: str, *, next_date: str | None = None,
                  next_eps: float | None = None, next_rev: float | None = None,
                  earnings: list[EarningsPoint] | None = None) -> None:
    """Inject a Fundamentals row into the service-level cache."""
    f = Fundamentals(
        ticker=ticker,
        next_earnings_date=next_date,
        next_eps_estimate=next_eps,
        next_revenue_estimate=next_rev,
        earnings=earnings or [],
        fetched_at=datetime.now(UTC).timestamp(),
    )
    stock_fundamentals_service._CACHE[ticker] = f


# ---------------------------------------------------------------------------
# Earnings aggregation
# ---------------------------------------------------------------------------

def test_get_events_returns_earnings_from_next_earnings_date(db: Session):
    _seed_stock_with_score(
        db, ticker="AAPL", name="Apple Inc.", sector="Technology",
        market_cap=3_000_000_000_000,
    )
    _put_in_cache("AAPL", next_date="2026-05-08", next_eps=1.43, next_rev=90_000_000_000.0)

    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))

    earnings = [e for e in events if isinstance(e, EarningsEvent)]
    assert len(earnings) == 1
    e = earnings[0]
    assert e.ticker == "AAPL"
    assert e.date == date(2026, 5, 8)
    assert e.name == "Apple Inc."
    assert e.eps_estimate == pytest.approx(1.43)
    assert e.revenue_estimate == pytest.approx(90_000_000_000.0)
    assert e.sector == "Technology"
    assert e.market_cap == 3_000_000_000_000


def test_get_events_includes_historical_earnings_in_window(db: Session):
    _seed_stock_with_score(db, ticker="MSFT", name="Microsoft", sector="Technology")
    _put_in_cache(
        "MSFT",
        next_date=None,
        earnings=[
            EarningsPoint(date="2026-04-25", eps_estimate=2.5, eps_reported=2.7, surprise_pct=8.0),
            EarningsPoint(date="2026-05-15", eps_estimate=2.6, eps_reported=2.8, surprise_pct=7.7),
        ],
    )

    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))
    earnings = [e for e in events if isinstance(e, EarningsEvent)]

    # Only the May 15 print falls in window
    assert len(earnings) == 1
    assert earnings[0].date == date(2026, 5, 15)
    assert earnings[0].ticker == "MSFT"
    assert earnings[0].eps_estimate == pytest.approx(2.6)


def test_get_events_excludes_earnings_outside_window(db: Session):
    _seed_stock_with_score(db, ticker="GOOG", name="Alphabet")
    _put_in_cache("GOOG", next_date="2026-04-15", next_eps=1.1)
    _put_in_cache("GOOG", next_date="2026-04-15", next_eps=1.1,
                  earnings=[EarningsPoint(date="2026-04-15", eps_estimate=1.1,
                                          eps_reported=1.2, surprise_pct=9.0)])

    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))
    earnings = [e for e in events if isinstance(e, EarningsEvent)]
    assert earnings == []


def test_get_events_skips_unscored_stocks(db: Session):
    """A stock without a StockScore row must not appear, even if its
    fundamentals are cached."""
    s = Stock(ticker="UNSCORED", exchange="NMS", name="No Score Inc.")
    db.add(s)
    db.commit()
    _put_in_cache("UNSCORED", next_date="2026-05-10", next_eps=0.5)

    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))
    assert all(
        not (isinstance(e, EarningsEvent) and e.ticker == "UNSCORED")
        for e in events
    )


def test_get_events_skips_stocks_with_cold_cache(db: Session):
    """Scored stock with no fundamentals in cache → no earnings event,
    and crucially no network call (we never invoke get_fundamentals here)."""
    _seed_stock_with_score(db, ticker="COLD", name="Cold Inc.")
    # NOT calling _put_in_cache → cache is empty
    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))
    assert all(
        not (isinstance(e, EarningsEvent) and e.ticker == "COLD")
        for e in events
    )


def test_get_events_dedupes_when_next_overlaps_with_history(db: Session):
    """If next_earnings_date and an earnings[] entry have the same date,
    we emit one event (not two)."""
    _seed_stock_with_score(db, ticker="DUP", name="Dup Co.")
    _put_in_cache(
        "DUP",
        next_date="2026-05-15",
        next_eps=1.0,
        earnings=[EarningsPoint(date="2026-05-15", eps_estimate=1.0,
                                eps_reported=None, surprise_pct=None)],
    )
    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))
    earnings = [e for e in events if isinstance(e, EarningsEvent) and e.ticker == "DUP"]
    assert len(earnings) == 1


# ---------------------------------------------------------------------------
# Macro filtering
# ---------------------------------------------------------------------------

def test_get_events_includes_macros_in_window(db: Session):
    """Pick a window that's known to contain at least one curated macro."""
    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))
    macros = [e for e in events if isinstance(e, MacroEventDC)]
    assert len(macros) >= 1
    # FOMC May 14 should be in the curated list
    assert any(m.date == date(2026, 5, 14) and "FOMC" in m.label for m in macros)


def test_macros_importance_filter_excludes_non_high(db: Session):
    """importance={high} drops medium/low macros (PPI is medium in our seed)."""
    events = calendar_service.get_events(
        db, date(2026, 5, 1), date(2026, 5, 31),
        importance={"high"},
    )
    macros = [e for e in events if isinstance(e, MacroEventDC)]
    assert macros, "expected some high-importance macros in May"
    assert all(m.importance == "high" for m in macros)


def test_kinds_earnings_excludes_macros(db: Session):
    _seed_stock_with_score(db, ticker="AAPL", name="Apple Inc.")
    _put_in_cache("AAPL", next_date="2026-05-08", next_eps=1.0)

    events = calendar_service.get_events(
        db, date(2026, 5, 1), date(2026, 5, 31), kinds={"earnings"},
    )
    assert all(isinstance(e, EarningsEvent) for e in events)
    assert any(isinstance(e, EarningsEvent) and e.ticker == "AAPL" for e in events)


def test_kinds_macro_excludes_earnings(db: Session):
    _seed_stock_with_score(db, ticker="AAPL", name="Apple Inc.")
    _put_in_cache("AAPL", next_date="2026-05-08", next_eps=1.0)

    events = calendar_service.get_events(
        db, date(2026, 5, 1), date(2026, 5, 31), kinds={"macro"},
    )
    assert all(isinstance(e, MacroEventDC) for e in events)


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------

def test_events_sorted_by_date_ascending(db: Session):
    _seed_stock_with_score(db, ticker="AAA", name="A")
    _seed_stock_with_score(db, ticker="BBB", name="B")
    _put_in_cache("AAA", next_date="2026-05-20", next_eps=1.0)
    _put_in_cache("BBB", next_date="2026-05-05", next_eps=1.0)

    events = calendar_service.get_events(db, date(2026, 5, 1), date(2026, 5, 31))
    dates = [e.date for e in events]
    assert dates == sorted(dates)


def test_within_a_day_macros_come_before_earnings(db: Session):
    """May 14 has FOMC (macro). Plant an earnings on the same day → macro first.

    Macros are scarcer + higher signal at a glance, so they anchor the cell
    preview ahead of the long tail of per-stock earnings releases. (Previously
    earnings came first; reversed in the calendar UX rework — see
    docs/calendar-page.md V2 notes.)
    """
    from app.services.calendar_service import MacroEventDC
    _seed_stock_with_score(db, ticker="ZZZ", name="Z Co.")
    _put_in_cache("ZZZ", next_date="2026-05-14", next_eps=1.0)

    events = calendar_service.get_events(db, date(2026, 5, 14), date(2026, 5, 14))
    same_day = [e for e in events if e.date == date(2026, 5, 14)]
    assert len(same_day) >= 2  # at least the earnings + the FOMC macro
    # First event for the day must be the FOMC macro (high importance)
    assert isinstance(same_day[0], MacroEventDC)
    assert same_day[0].label.startswith("FOMC")
    # And our earnings is somewhere later in the same-day cohort
    assert any(
        isinstance(e, EarningsEvent) and e.ticker == "ZZZ" for e in same_day
    )


# ---------------------------------------------------------------------------
# calendar_macros direct tests
# ---------------------------------------------------------------------------

def test_macro_get_events_filters_by_window_inclusive():
    out = calendar_macros.get_macro_events(date(2026, 5, 14), date(2026, 5, 14))
    # FOMC + PPI are both on May 14 in our seed
    assert any(m.label.startswith("FOMC") for m in out)
    assert all(m.date == date(2026, 5, 14) for m in out)


def test_macro_get_events_empty_window_returns_empty_list():
    # A window in the distant past where we have no curated events.
    out = calendar_macros.get_macro_events(date(2020, 1, 1), date(2020, 1, 31))
    assert out == []


def test_macro_get_events_importance_filter_high_only():
    out = calendar_macros.get_macro_events(
        date(2026, 5, 1), date(2026, 8, 31), importance_filter={"high"},
    )
    assert out
    assert all(m.importance == "high" for m in out)
