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
    ):
        with pytest.raises(UpstreamTimeout):
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

    with patch("yfinance.Ticker", return_value=fake_ticker):
        with pytest.raises(UpstreamTimeout):
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
