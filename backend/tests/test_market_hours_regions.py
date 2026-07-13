"""Exchange-region mapping for market-hours checks.

Unknown suffixes falling through to 'US' silently disabled the
unsettled-today-bar ingest guard for .T/.KS/.OL/.AX/.IL listings (a Tokyo
stock judged on New York hours). Every exchange in the catalog must map.
"""
from datetime import UTC, datetime

from app.services.live_quote_service import _exchange_region, _is_market_open


def test_suffix_region_mapping():
    assert _exchange_region("7203.T") == "JP"
    assert _exchange_region("005930.KS") == "KR"
    assert _exchange_region("EQNR.OL") == "NO"
    assert _exchange_region("BHP.AX") == "AU"
    assert _exchange_region("SHEL.IL") == "UK"    # London IOB trades LSE hours
    assert _exchange_region("BT-A.L") == "UK"
    assert _exchange_region("AAPL") == "US"


def test_tokyo_hours_not_new_york():
    # Tuesday 01:00 UTC = 10:00 JST → Tokyo OPEN (was CLOSED under the US map,
    # which is what let in-flight .T bars persist as settled closes).
    open_jst = datetime(2026, 6, 23, 1, 0, tzinfo=UTC)
    assert _is_market_open("7203.T", now_utc=open_jst) is True
    # Tuesday 15:00 UTC = 00:00 JST (next day) → Tokyo CLOSED, but 11:00 in
    # New York — under the old US fallback this reported OPEN.
    closed_jst = datetime(2026, 6, 23, 15, 0, tzinfo=UTC)
    assert _is_market_open("7203.T", now_utc=closed_jst) is False
