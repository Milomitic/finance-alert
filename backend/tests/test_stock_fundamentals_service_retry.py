"""Il fetch fundamentals deve ri-tentare su timeout simulato."""
from unittest.mock import patch

import pytest

from app.core.errors import UpstreamTimeout
from app.services.stock_fundamentals_service import _yf_fetch_with_retry


def test_yf_fetch_retries_on_timeout_then_succeeds():
    calls = {"n": 0}

    def fake_do(_t: str):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("simulated network timeout")
        return {"ok": True}

    with patch(
        "app.services.stock_fundamentals_service._do_yf_call", side_effect=fake_do
    ):
        result = _yf_fetch_with_retry("AAPL")
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_yf_fetch_gives_up_after_retries():
    def fake_do(_t: str):
        raise TimeoutError("persistent")

    with patch(
        "app.services.stock_fundamentals_service._do_yf_call", side_effect=fake_do
    ), pytest.raises(UpstreamTimeout):
        _yf_fetch_with_retry("AAPL")


def test_per_endpoint_timeout_inside_do_yf_call_is_re_raised_for_retry():
    """A TimeoutError raised on a single endpoint inside _do_yf_call must
    propagate as UpstreamTimeout (so the outer wrapper can retry it),
    NOT be silently swallowed as None.

    This is the behavior the retry layer was added to provide. Before the
    fix, per-endpoint exceptions were caught locally and the retry never
    fired — making the retry layer a no-op for the dominant failure mode
    (a slow yfinance endpoint, not a dead Ticker constructor)."""
    from unittest.mock import MagicMock

    from app.services import stock_fundamentals_service

    # Build a fake Ticker whose get_info() call raises TimeoutError.
    # yf is imported locally inside _do_yf_call, so patch yfinance.Ticker directly.
    fake_ticker = MagicMock()
    fake_ticker.income_stmt = None
    fake_ticker.quarterly_income_stmt = None
    fake_ticker.earnings_dates = None
    fake_ticker.get_info.side_effect = TimeoutError("network timeout")
    fake_ticker.insider_transactions = None
    fake_ticker.recommendations = None
    fake_ticker.analyst_price_targets = None
    fake_ticker.upgrades_downgrades = None

    with patch("yfinance.Ticker", return_value=fake_ticker), pytest.raises(UpstreamTimeout):
        stock_fundamentals_service._do_yf_call("AAPL")


def test_per_endpoint_value_error_is_swallowed_not_re_raised():
    """Non-retryable errors (KeyError, ValueError, etc.) inside a single
    endpoint must NOT trigger a retry — they degrade to None for that key
    and the rest of the payload is returned. This preserves the partial-
    payload behavior that pre-dated the retry layer."""
    from unittest.mock import MagicMock

    from app.services import stock_fundamentals_service

    # get_info() raises ValueError — non-retryable, must be swallowed.
    fake_ticker = MagicMock()
    fake_ticker.income_stmt = None
    fake_ticker.quarterly_income_stmt = None
    fake_ticker.earnings_dates = None
    fake_ticker.get_info.side_effect = ValueError("bad shape")
    fake_ticker.insider_transactions = None
    fake_ticker.recommendations = None
    fake_ticker.analyst_price_targets = None
    fake_ticker.upgrades_downgrades = None

    with patch("yfinance.Ticker", return_value=fake_ticker):
        # Should NOT raise — ValueError is not retryable.
        out = stock_fundamentals_service._do_yf_call("AAPL")
    assert out["info"] is None


def test_hydrate_l1_from_db_returns_loaded_and_skipped_counts(db):
    """hydrate_l1_from_db deve tornare una tupla (loaded:int, skipped:int)
    invece di un int singolo, così il caller può loggare entrambi."""
    from app.services import stock_fundamentals_service
    # Su DB vuoto: 0 loaded, 0 skipped.
    result = stock_fundamentals_service.hydrate_l1_from_db()
    assert isinstance(result, tuple)
    assert result == (0, 0)


def _raw_payload(**overrides):
    """A complete raw-fetch dict (the shape `_do_yf_call` / `_yf_fetch_with_retry`
    return) with every endpoint None unless overridden."""
    base = {
        "income_stmt": None,
        "quarterly_income_stmt": None,
        "earnings_dates": None,
        "info": None,
        "insider_transactions": None,
        "recommendations": None,
        "analyst_price_targets": None,
        "upgrades_downgrades": None,
        "earnings_estimate": None,
        "revenue_estimate": None,
    }
    base.update(overrides)
    return base


def test_curr_fy_projection_overrides_trailing_yoy(monkeypatch):
    """When the estimate tables yield a 0y growth, micro.earnings_growth /
    micro.revenue_growth end up equal to the PROJECTED value — not the
    trailing-YoY value yfinance's info gave."""
    import pandas as pd

    from app.services import stock_fundamentals_service as svc
    from app.services import yfinance_health

    yfinance_health.reset()

    eps_est = pd.DataFrame({"growth": [0.30]}, index=["0y"])
    rev_est = pd.DataFrame({"growth": [0.25]}, index=["0y"])
    # info gives trailing YoY of +5% / +6% — should be overridden.
    info = {"earningsGrowth": 0.05, "revenueGrowth": 0.06}

    monkeypatch.setattr(
        svc, "_yf_fetch_with_retry",
        lambda _t: _raw_payload(info=info, earnings_estimate=eps_est, revenue_estimate=rev_est),
    )

    f = svc._fetch_fresh("AAPL")
    # Raw projection stored for transparency …
    assert f.micro.eps_growth_curr_fy == 0.30
    assert f.micro.revenue_growth_curr_fy == 0.25
    # … and it WON the swap over trailing YoY.
    assert f.micro.earnings_growth == 0.30
    assert f.micro.revenue_growth == 0.25


def test_trailing_yoy_kept_when_projection_absent(monkeypatch):
    """No estimate tables → curr-FY fields stay None and the trailing/
    reconciled YoY from info flows through unchanged."""
    from app.services import stock_fundamentals_service as svc
    from app.services import yfinance_health

    yfinance_health.reset()

    info = {"earningsGrowth": 0.05, "revenueGrowth": 0.06}
    monkeypatch.setattr(
        svc, "_yf_fetch_with_retry",
        lambda _t: _raw_payload(info=info),  # no estimate tables
    )

    f = svc._fetch_fresh("AAPL")
    assert f.micro.eps_growth_curr_fy is None
    assert f.micro.revenue_growth_curr_fy is None
    # Trailing YoY preserved (no reported series to reconcile against).
    assert f.micro.earnings_growth == 0.05
    assert f.micro.revenue_growth == 0.06


def test_breaker_records_failure_on_each_retry_attempt(monkeypatch):
    """The retry loop must inform yfinance_health on every attempt failure,
    not just the final exhaustion. Without this, with retries=3 the breaker
    sees only 1 record per user call instead of 4 (1 initial + 3 retries),
    and its 5-failure threshold takes ~5x longer to trip than designed."""
    from app.services import stock_fundamentals_service, yfinance_health

    yfinance_health.reset()
    # No-op sleep so retries don't actually wait the 0.5/1.0/2.0s backoffs.
    monkeypatch.setattr("app.services._retry.time.sleep", lambda _s: None)

    def always_429(_t):
        # The string "Too Many Requests" makes `_normalize_yf_error` classify
        # this as a RateLimitError, which is retryable AND satisfies
        # `yfinance_health.is_rate_limit_error` heuristic.
        raise RuntimeError("Too Many Requests")

    monkeypatch.setattr(
        stock_fundamentals_service, "_do_yf_call", always_429
    )

    with pytest.raises(Exception):
        stock_fundamentals_service._yf_fetch_with_retry("AAPL")

    status = yfinance_health.status()
    # The retry decorator uses "total attempts" semantic: retries=3 means
    # 3 total attempts (not 1 initial + 3 retries). Each failed attempt
    # records to the breaker, so we expect 3 records, not 1.
    assert status["failures_in_window"] == 3, (
        f"expected exactly 3 breaker records after retry exhaustion "
        f"(retries=3 = 3 total attempts), got: {status}"
    )

    yfinance_health.reset()  # leave clean for other tests
