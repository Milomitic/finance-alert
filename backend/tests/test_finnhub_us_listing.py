"""Finnhub is only asked about symbols its plan actually covers.

Production measurement behind this: 469 Forbidden responses in the retained
log window, split MI 14 / L 10 / T 10 / KS 6 / DE 4 / HK 4 / HE 1 — and not
one on a bare ticker. Each was a network round-trip made in order to be told
no, every day, forever.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.services import finnhub_earnings_service as svc


class TestIsUsListed:
    @pytest.mark.parametrize("sym", ["AAPL", "MSFT", "NVDA", "F", "BRK-B", "BF-B"])
    def test_bare_tickers_are_us_listed(self, sym):
        """Dashes are not a suffix. BRK-B and BF-B were renamed FROM dot form
        so yfinance would accept them; reading the dash as a market separator
        would drop two S&P 500 names."""
        assert svc.is_us_listed(sym) is True

    @pytest.mark.parametrize(
        "sym", ["TEN.MI", "SIE.DE", "0700.HK", "BT-A.L", "005930.KS", "7203.T"],
    )
    def test_exchange_suffixes_are_not(self, sym):
        assert svc.is_us_listed(sym) is False

    @pytest.mark.parametrize("sym", ["TSM", "BIDU", "SPOT", "RACE", "NVO", "PBR"])
    def test_adrs_are_us_listed_even_though_the_company_is_not(self, sym):
        """THE REGRESSION THAT MATTERS.

        These are foreign companies trading on NYSE/NASDAQ. Filtering on
        `Stock.country` instead of the listing would drop 25 catalogue symbols
        that Finnhub serves perfectly well — and none of them ever appears
        among the 403s. The predicate is about where the share trades, not
        where the company is domiciled.
        """
        assert svc.is_us_listed(sym) is True

    @pytest.mark.parametrize("sym", ["", None])
    def test_no_symbol_does_not_raise(self, sym):
        # Runs inside a scheduled job; an exception here costs the whole batch.
        assert svc.is_us_listed(sym) is False


class TestFetchCalendarSkipsForeignListings:
    @pytest.fixture(autouse=True)
    def _enabled(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "finnhub_api_key", "k" * 20)

    def test_a_foreign_symbol_makes_no_request(self):
        with patch.object(svc.requests, "get") as get:
            out = svc.fetch_calendar(
                from_date=date(2026, 8, 1), to_date=date(2026, 8, 19), symbol="TEN.MI",
            )
        assert out == []
        get.assert_not_called()

    def test_a_us_symbol_still_requests(self):
        with patch.object(svc.requests, "get") as get:
            get.return_value.json.return_value = {"earningsCalendar": []}
            get.return_value.raise_for_status.return_value = None
            svc.fetch_calendar(
                from_date=date(2026, 8, 1), to_date=date(2026, 8, 19), symbol="AAPL",
            )
        get.assert_called_once()

    def test_the_whole_window_call_is_not_filtered(self):
        """symbol=None is the un-narrowed US calendar fetch — the one that
        works. Skipping it because it has no symbol would disable the feature
        outright."""
        with patch.object(svc.requests, "get") as get:
            get.return_value.json.return_value = {"earningsCalendar": []}
            get.return_value.raise_for_status.return_value = None
            svc.fetch_calendar(from_date=date(2026, 8, 1), to_date=date(2026, 8, 19))
        get.assert_called_once()

    def test_recent_actuals_skips_foreign_but_keeps_us(self):
        with patch.object(svc.requests, "get") as get:
            get.return_value.json.return_value = {"earningsCalendar": []}
            get.return_value.raise_for_status.return_value = None
            svc.fetch_recent_actuals(["AAPL", "TEN.MI", "0700.HK", "MSFT"])
        # Two US names asked, two foreign ones never left the process.
        assert get.call_count == 2
