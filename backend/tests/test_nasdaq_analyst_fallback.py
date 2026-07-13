"""Nasdaq (key-less) analyst consensus — tier-3 fallback behind
yfinance + Finnhub for recommendation buckets AND price target.

Unit-tests the parser/cache/breaker against a mocked urllib response,
plus an integration test that drives `_fetch_fresh` with empty yfinance
+ empty Finnhub and asserts Nasdaq fills both axes. A network smoke test
(opt-in via RUN_NETWORK_TESTS=1) confirms the live shape still parses.
"""
from __future__ import annotations

import io
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.services import nasdaq_analyst_service as na

# Real-shape fixture (trimmed from a live api.nasdaq.com response).
_BODY = {
    "data": {
        "symbol": "aapl",
        "consensusOverview": {
            "lowPriceTarget": 250.0, "highPriceTarget": 400.0,
            "priceTarget": 318.75, "buy": 17, "sell": 1, "hold": 10,
        },
        "historicalConsensus": [
            {"z": {"buy": 16, "hold": 8, "sell": 4, "date": "03/01/2026", "consensus": "Buy"}, "x": 1, "y": 200.0},
            {"z": {"buy": 15, "hold": 9, "sell": 4, "date": "04/01/2026", "consensus": "Buy"}, "x": 2, "y": 210.0},
            {"z": {"buy": 17, "hold": 10, "sell": 1, "date": "05/01/2026", "consensus": "Buy"}, "x": 3, "y": 220.0},
        ],
    },
    "message": None,
    "status": {"rCode": 200},
}


def _urlopen_returning(body: object) -> MagicMock:
    """Build a urlopen replacement whose context-manager yields an
    object with .read() == json(body)."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(
        return_value=io.BytesIO(json.dumps(body).encode("utf-8"))
    )
    cm.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=cm)


def setup_function() -> None:
    from app.core import breaker_state
    na._CACHE.clear()
    na._RATE_TIMESTAMPS.clear()
    na._BLOCKED_UNTIL = None
    breaker_state.clear(na._BREAKER_KEY)  # don't leak a persisted breaker


def teardown_function() -> None:
    """The breaker test persists to breakers.json — clear it so the open
    state can't leak into the running app or other test processes."""
    from app.core import breaker_state
    na._BLOCKED_UNTIL = None
    breaker_state.clear(na._BREAKER_KEY)


def test_parses_buckets_newest_first_and_price_target() -> None:
    with patch("urllib.request.urlopen", _urlopen_returning(_BODY)):
        out = na.fetch_analyst("AAPL")
    assert out is not None
    # Price target from consensusOverview.
    assert out.pt_low == 250.0 and out.pt_high == 400.0 and out.pt_mean == 318.75
    # historicalConsensus is ascending → newest first after reverse.
    assert [b.period for b in out.buckets] == ["0m", "-1m", "-2m"]
    assert out.buckets[0].buy == 17 and out.buckets[0].hold == 10 and out.buckets[0].sell == 1
    # Nasdaq has no strong-buy/strong-sell split.
    assert out.buckets[0].strong_buy == 0 and out.buckets[0].strong_sell == 0


def test_caches_per_ticker() -> None:
    fake = _urlopen_returning(_BODY)
    with patch("urllib.request.urlopen", fake):
        na.fetch_analyst("AAPL")
        na.fetch_analyst("AAPL")
    # Second call served from the 24h cache → only ONE round-trip.
    assert fake.call_count == 1


def test_breaker_opens_on_403() -> None:
    import urllib.error
    err = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    with patch("urllib.request.urlopen", MagicMock(side_effect=err)):
        assert na.fetch_analyst("AAPL") is None
    blocked, _ = na._is_blocked()
    assert blocked is True
    # teardown_function clears the persisted breaker.


def test_empty_payload_returns_none_and_caches() -> None:
    with patch("urllib.request.urlopen", _urlopen_returning({"data": None})):
        assert na.fetch_analyst("ZZZZ") is None
    # Cached as None so a scan doesn't hammer the endpoint for a name
    # Nasdaq doesn't cover.
    assert "ZZZZ" in na._CACHE and na._CACHE["ZZZZ"][1] is None


# ─── integration: yfinance + Finnhub empty → Nasdaq fills both axes ──

def test_fetch_fresh_uses_nasdaq_when_yfinance_and_finnhub_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pandas as pd

    from app.services import stock_fundamentals_service as sfs

    class EmptyTicker:
        """Every yfinance endpoint empty → ratings + price_target stay
        blank, so the Nasdaq fallback path is exercised."""
        def __init__(self, _t: str) -> None:
            pass
        @property
        def income_stmt(self): return pd.DataFrame()
        @property
        def quarterly_income_stmt(self): return pd.DataFrame()
        @property
        def earnings_dates(self): return pd.DataFrame()
        def get_info(self): return {}
        @property
        def insider_transactions(self): return pd.DataFrame()
        @property
        def recommendations(self): return pd.DataFrame()
        @property
        def analyst_price_targets(self): return {}
        @property
        def upgrades_downgrades(self): return pd.DataFrame()

    monkeypatch.setattr("yfinance.Ticker", EmptyTicker)
    # Finnhub fallback returns nothing (e.g. breaker open).
    monkeypatch.setattr(
        "app.services.finnhub_news_service.fetch_recommendation_trend",
        lambda _t: [],
    )
    # Nasdaq has the data.
    monkeypatch.setattr(
        "app.services.nasdaq_analyst_service.fetch_analyst",
        lambda _t: na.NasdaqAnalyst(
            buckets=[na.NasdaqRatingBucket("0m", 0, 17, 10, 1, 0)],
            pt_low=250.0, pt_high=400.0, pt_mean=318.75,
        ),
    )

    f = sfs._fetch_fresh("AAPL")
    # Recommendation buckets filled from Nasdaq...
    assert f.analyst_ratings and f.analyst_ratings[0].buy == 17
    # ...and the price target too.
    assert f.price_target.mean == 318.75
    assert f.price_target.low == 250.0 and f.price_target.high == 400.0


@pytest.mark.skipif(
    os.getenv("RUN_NETWORK_TESTS") != "1",
    reason="hits live api.nasdaq.com; opt-in via RUN_NETWORK_TESTS=1",
)
def test_live_shape_still_parses() -> None:  # pragma: no cover - network
    out = na.fetch_analyst("AAPL")
    assert out is not None
    assert out.pt_mean is not None
    assert out.buckets  # at least one consensus bucket
