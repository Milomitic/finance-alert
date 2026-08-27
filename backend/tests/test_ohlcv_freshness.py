"""A fetch counts as proof of life only if it brought a RECENT bar.

Four symbols rotted unnoticed because it did not. Measured in production on
2026-08-26: SATS, NUVL, CPRX and EA had no new bar for 16 to 40 days while
sitting at `ohlcv_nodata_streak = 0` — so they never reached the quarantine
threshold, were re-fetched forever, and nothing anywhere reported that their
data had stopped moving. yfinance can answer a request for a halted or
delisted symbol with the history it still holds, and that stale frame reset
the very counter meant to notice the symbol had died.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.ohlcv_service import _FRESH_WITHIN_DAYS, _frame_is_fresh

TODAY = date(2026, 8, 26)


def _frame(*days_old: int) -> pd.DataFrame:
    idx = pd.to_datetime([TODAY - timedelta(days=d) for d in sorted(days_old, reverse=True)])
    return pd.DataFrame({"close": [1.0] * len(days_old)}, index=idx)


class TestFreshness:
    @pytest.mark.parametrize("days", [0, 1, 3, 4, _FRESH_WITHIN_DAYS])
    def test_a_recent_bar_is_proof_of_life(self, days):
        assert _frame_is_fresh(_frame(days), TODAY) is True

    def test_a_long_weekend_does_not_start_a_streak(self):
        """The window has to absorb two weekend days plus a four- or five-day
        national closure without a single healthy stock being touched."""
        assert _frame_is_fresh(_frame(7), TODAY) is True

    @pytest.mark.parametrize("ticker,days", [("EA", 16), ("CPRX", 36), ("SATS", 40), ("CTRA", 111)])
    def test_the_symbols_that_rotted_are_caught(self, ticker, days):
        assert _frame_is_fresh(_frame(days), TODAY) is False

    def test_only_the_newest_bar_matters(self):
        """A backfill can deliver years of old rows alongside a current one.
        The presence of history says nothing; the newest date says everything."""
        assert _frame_is_fresh(_frame(400, 200, 1), TODAY) is True
        assert _frame_is_fresh(_frame(400, 200, 40), TODAY) is False


class TestNeverRaises:
    """This runs inside the per-stock fetch loop, where an exception costs the
    rest of the chunk — the exact failure the savepoint below it exists for."""

    def test_an_empty_frame_is_not_fresh(self):
        assert _frame_is_fresh(pd.DataFrame({"close": []}), TODAY) is False

    def test_a_malformed_index_is_not_fresh(self):
        bad = pd.DataFrame({"close": [1.0, 2.0]}, index=["non", "date"])
        assert _frame_is_fresh(bad, TODAY) is False

    def test_none_does_not_raise(self):
        assert _frame_is_fresh(None, TODAY) is False  # type: ignore[arg-type]
