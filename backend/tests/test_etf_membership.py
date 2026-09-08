"""Which ETFs hold this stock — the REVERSE of `get_holdings`.

The forward direction already existed: `get_holdings(db, "SPY")` returns SPY's
top positions, cached in `fetch_cache` under kind="etf_holdings". Inverting that
cache answers the question the stock-detail page wants instead: given NVDA,
which funds carry it.

⚠️ INVERTING IT LITERALLY ASSERTS MEMBERSHIPS THAT DO NOT EXIST, and the live
cache shows exactly that. Read straight, it returns

    NVDA -> SOXL, QQQ, SOXX, SPY, XLK, SOXS

with SOXL (3x bull semiconductors) and SOXS (3x bear) BOTH present. NVDA is
inside neither: a leveraged fund holds swaps on the index, and `get_holdings`
deliberately SUBSTITUTES the physical ETF's basket for them
(`_LEVERAGED_UNDERLYING`) so its components view has something to show. Those
cached rows are a stand-in, not a holdings list, so the reverse map has to undo
the substitution — otherwise the page claims a stock sits in a fund and in its
inverse at the same time.

The other honesty constraint is the cap. `_MAX_HOLDINGS = 25`, so this answers
"is among the largest positions of", never "is a member of". SPY has 503
constituents; a stock at rank 200 correctly gets no SPY label, and the UI must
say which of the two claims it is making.
"""

import json

import pytest

from app.models.fetch_cache import FetchCache
from app.services.etf_holdings_service import _CACHE_V, etfs_containing


def _cache(db, ticker: str, symbols: list[str], version: int = _CACHE_V) -> None:
    db.add(
        FetchCache(
            ticker=ticker,
            kind="etf_holdings",
            payload=json.dumps(
                {
                    "v": version,
                    "holdings": [
                        {"symbol": s, "name": s, "weight": 0.05} for s in symbols
                    ],
                }
            ),
        )
    )
    db.commit()


class TestLeveragedFundsCollapseOntoTheirUnderlying:
    def test_a_leveraged_fund_is_reported_as_its_underlying(self, db):
        # SOXL's cached "holdings" are SOXX's basket, substituted by
        # get_holdings. The stock is in SOXX, not in SOXL.
        _cache(db, "SOXL", ["NVDA", "AVGO"])
        assert etfs_containing(db, "NVDA") == ["SOXX"]

    def test_the_bull_and_the_bear_collapse_to_ONE_entry(self, db):
        # This is the defect the reverse map exists to avoid: SOXL and SOXS
        # carry the same substituted basket, so a literal inversion would put
        # a stock inside a fund and its inverse simultaneously.
        _cache(db, "SOXL", ["NVDA"])
        _cache(db, "SOXS", ["NVDA"])
        assert etfs_containing(db, "NVDA") == ["SOXX"]

    def test_a_physical_etf_is_reported_as_itself(self, db):
        _cache(db, "XLK", ["NVDA"])
        assert etfs_containing(db, "NVDA") == ["XLK"]

    def test_the_underlying_is_not_duplicated_when_both_are_cached(self, db):
        # SOXX is cached in its own right AND as SOXL's stand-in.
        _cache(db, "SOXX", ["NVDA"])
        _cache(db, "SOXL", ["NVDA"])
        assert etfs_containing(db, "NVDA") == ["SOXX"]


class TestWhatItReports:
    def test_a_stock_in_nothing_gets_an_empty_list(self, db):
        _cache(db, "XLK", ["NVDA"])
        assert etfs_containing(db, "KO") == []

    def test_results_are_sorted_so_the_ui_is_stable(self, db):
        _cache(db, "XLK", ["NVDA"])
        _cache(db, "SPY", ["NVDA"])
        _cache(db, "QQQ", ["NVDA"])
        assert etfs_containing(db, "NVDA") == ["QQQ", "SPY", "XLK"]

    def test_the_symbol_match_ignores_case(self, db):
        _cache(db, "XLK", ["nvda"])
        assert etfs_containing(db, "NVDA") == ["XLK"]

    def test_an_etf_does_not_report_itself(self, db):
        # SPY appears inside some funds-of-funds; listing "SPY is in SPY"
        # would be noise on SPY's own page.
        _cache(db, "SPY", ["SPY", "NVDA"])
        assert etfs_containing(db, "SPY") == []


class TestItNeverThrowsOnBadCacheRows:
    """A detail page must not 500 because one cached row is malformed."""

    def test_a_stale_schema_version_is_skipped_not_parsed(self, db):
        _cache(db, "XLK", ["NVDA"], version=_CACHE_V - 1)
        assert etfs_containing(db, "NVDA") == []

    def test_corrupt_json_is_skipped(self, db):
        db.add(FetchCache(ticker="XLK", kind="etf_holdings", payload="{not json"))
        db.commit()
        _cache(db, "SPY", ["NVDA"])
        assert etfs_containing(db, "NVDA") == ["SPY"]

    def test_an_empty_holdings_row_contributes_nothing(self, db):
        # A regular equity's non-ETF result is cached as [] on purpose.
        _cache(db, "KO", [])
        assert etfs_containing(db, "NVDA") == []


@pytest.mark.parametrize("ticker", ["", "   "])
def test_a_blank_ticker_asks_nothing_of_the_cache(db, ticker):
    _cache(db, "XLK", ["NVDA"])
    assert etfs_containing(db, ticker) == []
