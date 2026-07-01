"""A transient yfinance failure must not poison the cache: it should never
turn into a guaranteed 404 for the full 15min TTL once yfinance recovers."""
from unittest.mock import patch

from app.services import market_detail_service as svc


def teardown_function() -> None:
    svc.clear_cache()


def test_failed_fetch_is_not_cached_as_none():
    with patch.object(svc, "_fetch_fresh", return_value=None) as fetch:
        assert svc.get_detail("^GSPC", "1d") is None
        assert svc.get_detail("^GSPC", "1d") is None
        # Each call retried yfinance instead of short-circuiting on a
        # cached `None` — the old bug cached the failure for 15 minutes.
        assert fetch.call_count == 2


def test_failed_fetch_falls_back_to_stale_cached_value():
    good = svc.MarketDetailDC(symbol="^GSPC", range_key="1d")
    with patch.object(svc, "_fetch_fresh", return_value=good):
        assert svc.get_detail("^GSPC", "1d") is good

    # Force the cache to look expired, then simulate a rate-limited retry.
    key = ("^GSPC", "1d")
    with svc._CACHE_LOCK:
        ts, val = svc._CACHE[key]
        svc._CACHE[key] = (ts - svc._TTL_SECONDS - 1, val)

    with patch.object(svc, "_fetch_fresh", return_value=None):
        assert svc.get_detail("^GSPC", "1d") is good


def test_successful_fetch_is_cached_normally():
    good = svc.MarketDetailDC(symbol="^GSPC", range_key="1d")
    with patch.object(svc, "_fetch_fresh", return_value=good) as fetch:
        assert svc.get_detail("^GSPC", "1d") is good
        assert svc.get_detail("^GSPC", "1d") is good
        fetch.assert_called_once()
