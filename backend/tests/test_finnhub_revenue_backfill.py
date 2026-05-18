"""`_merge_finnhub_revenue` backfills revenue est/actual that yfinance
never provides (its earnings_dates feed is EPS-only)."""
from datetime import date
from unittest.mock import patch

from app.services.finnhub_earnings_service import FinnhubEarning
from app.services.stock_fundamentals_service import (
    EarningsPoint,
    Fundamentals,
    _merge_finnhub_revenue,
)


def _fund_with_eps_only_history() -> Fundamentals:
    """A Fundamentals as yfinance would leave it: EPS populated,
    revenue fields all None (yfinance earnings_dates has no revenue)."""
    f = Fundamentals(ticker="AAPL")
    f.earnings = [
        EarningsPoint(date="2026-02-01", eps_estimate=2.0, eps_reported=2.1,
                       surprise_pct=5.0, revenue_estimate=None,
                       revenue_reported=None),
        EarningsPoint(date="2026-04-30", eps_estimate=1.5, eps_reported=1.6,
                       surprise_pct=6.6, revenue_estimate=None,
                       revenue_reported=None),
    ]
    f.next_earnings_date = "2026-07-31"
    f.next_eps_estimate = 1.8
    f.next_revenue_estimate = None
    return f


def _fe(d: date, *, ea, ee, ra, re) -> FinnhubEarning:
    return FinnhubEarning(
        symbol="AAPL", date=d,
        eps_actual=ea, eps_estimate=ee,
        revenue_actual=ra, revenue_estimate=re,
        quarter=None, year=None, hour=None,
    )


def _finnhub_calendar() -> list[FinnhubEarning]:
    return [
        # Exact-date match for the first historical event
        _fe(date(2026, 2, 1), ea=2.1, ee=2.0, ra=120e9, re=118e9),
        # +1 day off vs yfinance's 2026-04-30 (tolerance must catch it)
        _fe(date(2026, 5, 1), ea=1.6, ee=1.5, ra=95e9, re=94e9),
        # Forward event — only estimate populated
        _fe(date(2026, 7, 31), ea=None, ee=1.8, ra=None, re=130e9),
    ]


def test_backfills_history_and_next_revenue():
    f = _fund_with_eps_only_history()
    with patch(
        "app.services.finnhub_earnings_service.is_enabled", return_value=True
    ), patch(
        "app.services.finnhub_earnings_service.fetch_calendar",
        return_value=_finnhub_calendar(),
    ):
        _merge_finnhub_revenue("AAPL", f)

    # Exact-date match
    assert f.earnings[0].revenue_estimate == 118e9
    assert f.earnings[0].revenue_reported == 120e9
    # ±1 day tolerance match (yfinance 04-30 ↔ Finnhub 05-01)
    assert f.earnings[1].revenue_estimate == 94e9
    assert f.earnings[1].revenue_reported == 95e9
    # Forward event estimate
    assert f.next_revenue_estimate == 130e9


def test_noop_when_finnhub_disabled():
    f = _fund_with_eps_only_history()
    with patch(
        "app.services.finnhub_earnings_service.is_enabled", return_value=False
    ):
        _merge_finnhub_revenue("AAPL", f)
    # Untouched — no key, no backfill
    assert f.earnings[0].revenue_estimate is None
    assert f.next_revenue_estimate is None


def test_noop_when_nothing_to_fill():
    """If every revenue field is already populated AND next estimate is
    set, the function must not even hit Finnhub."""
    f = Fundamentals(ticker="AAPL")
    f.earnings = [
        EarningsPoint(date="2026-02-01", eps_estimate=2.0, eps_reported=2.1,
                       surprise_pct=5.0, revenue_estimate=1.0,
                       revenue_reported=1.0),
    ]
    f.next_earnings_date = "2026-07-31"
    f.next_revenue_estimate = 2.0

    called = {"n": 0}

    def _spy(**_kw):
        called["n"] += 1
        return []

    with patch(
        "app.services.finnhub_earnings_service.is_enabled", return_value=True
    ), patch(
        "app.services.finnhub_earnings_service.fetch_calendar", side_effect=_spy
    ):
        _merge_finnhub_revenue("AAPL", f)
    assert called["n"] == 0  # short-circuited before the HTTP call


def test_does_not_overwrite_existing_revenue():
    """yfinance/Finnhub-actuals merge may have already set a value;
    the backfill only fills None gaps, never overwrites."""
    f = _fund_with_eps_only_history()
    f.earnings[0].revenue_reported = 999.0  # pre-existing value
    with patch(
        "app.services.finnhub_earnings_service.is_enabled", return_value=True
    ), patch(
        "app.services.finnhub_earnings_service.fetch_calendar",
        return_value=_finnhub_calendar(),
    ):
        _merge_finnhub_revenue("AAPL", f)
    # Pre-existing reported value preserved; only the None estimate filled
    assert f.earnings[0].revenue_reported == 999.0
    assert f.earnings[0].revenue_estimate == 118e9
