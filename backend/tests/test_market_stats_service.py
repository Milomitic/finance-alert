"""Tests for app.services.market_stats_service."""
import pandas as pd

from app.services.market_stats_service import (
    StockMetrics,
    compute_stock_metrics,
    derive_mood,
)
from tests.conftest_market import build_ohlcv, build_ohlcv_volume_spike


def test_compute_metrics_full_data():
    ohlcv = build_ohlcv(n_bars=250, start_close=100.0, drift=0.1)
    m = compute_stock_metrics(
        stock_id=1, ticker="X", sector="Tech",
        index_codes=["NDX"], market_cap=1_000_000_000.0, ohlcv=ohlcv,
    )
    assert m is not None
    assert m.has_full_data is True
    assert m.bars_count == 250
    assert m.last_close == 100.0 + 0.1 * 249
    assert m.prev_close == 100.0 + 0.1 * 248
    assert m.change_pct is not None and m.change_pct > 0
    assert m.sma50 is not None
    assert m.sma200 is not None
    assert m.rsi14 is not None
    assert m.high_252 == m.last_close       # ascending series → max is last
    assert m.new_52w_high is True
    assert m.new_52w_low is False
    assert m.near_52w_high is True


def test_compute_metrics_short_history_partial():
    ohlcv = build_ohlcv(n_bars=30, start_close=100.0, drift=0.1)
    m = compute_stock_metrics(
        stock_id=2, ticker="Y", sector=None,
        index_codes=[], market_cap=None, ohlcv=ohlcv,
    )
    assert m is not None
    assert m.has_full_data is False         # bars < 200
    assert m.sma200 is None                 # too short
    assert m.sma50 is None                  # too short for SMA50
    assert m.rsi14 is not None              # 30 bars enough for RSI14
    assert m.vol_avg_20 is not None         # 30 bars enough for 20-day avg


def test_compute_metrics_too_short_returns_none():
    ohlcv = build_ohlcv(n_bars=10)
    m = compute_stock_metrics(1, "Z", None, [], None, ohlcv)
    assert m is None


def test_compute_metrics_volume_spike():
    ohlcv = build_ohlcv_volume_spike(n_bars=30)
    m = compute_stock_metrics(1, "V", None, [], None, ohlcv)
    assert m is not None
    assert m.vol_ratio is not None and m.vol_ratio > 4.0


def test_derive_mood_bullish():
    assert derive_mood(pct_above_sma200=65.0, advancers=130, decliners=70) == "bullish"


def test_derive_mood_bearish():
    assert derive_mood(pct_above_sma200=35.0, advancers=70, decliners=130) == "bearish"


def test_derive_mood_neutral_by_breadth():
    assert derive_mood(pct_above_sma200=50.0, advancers=130, decliners=70) == "neutral"


def test_derive_mood_neutral_by_advancers():
    # high breadth but more decliners → neutral
    assert derive_mood(pct_above_sma200=70.0, advancers=80, decliners=120) == "neutral"
