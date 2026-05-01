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


from app.services.market_stats_service import (
    aggregate_by_index,
    aggregate_by_sector,
    aggregate_global,
)


def _metric(stock_id, ticker, *, sector=None, indices=None, change_pct=0.5,
            sma50=99.0, sma200=95.0, rsi14=50.0, near_high=False, near_low=False,
            new_high=False, new_low=False, vol_ratio=1.0, has_full=True,
            last_close=100.0):
    return StockMetrics(
        stock_id=stock_id, ticker=ticker, sector=sector,
        index_codes=indices or [], market_cap=1e9, bars_count=250,
        last_close=last_close, prev_close=last_close - 1.0,
        change_pct=change_pct, sma50=sma50, sma200=sma200, rsi14=rsi14,
        high_252=last_close, low_252=last_close - 10.0,
        near_52w_high=near_high, near_52w_low=near_low,
        new_52w_high=new_high, new_52w_low=new_low,
        vol_today=1_000_000, vol_avg_20=500_000.0, vol_ratio=vol_ratio,
        has_full_data=has_full,
    )


def test_aggregate_global_breadth():
    ms = [
        _metric(1, "A", change_pct=1.0, sma200=99.0, last_close=100.0, rsi14=72.0),
        _metric(2, "B", change_pct=-0.5, sma200=99.0, last_close=98.0, rsi14=25.0),
        _metric(3, "C", change_pct=2.0, sma200=99.0, last_close=110.0, rsi14=55.0),
    ]
    g = aggregate_global(ms)
    assert g["stocks_total"] == 3
    assert g["stocks_with_data"] == 3
    assert g["advancers"] == 2
    assert g["decliners"] == 1
    # 2 of 3 above sma200 (A: 100>99 ✓, B: 98<99 ✗, C: 110>99 ✓)
    assert g["pct_above_sma200"] == 66.7
    assert g["rsi_oversold_count"] == 1
    assert g["rsi_overbought_count"] == 1


def test_aggregate_global_empty():
    g = aggregate_global([])
    assert g["stocks_total"] == 0
    assert g["mood"] == "neutral"


def test_aggregate_by_index_buckets():
    ms = [
        _metric(1, "A", indices=["NDX", "SP500"], change_pct=1.0, sma200=90.0, last_close=100.0),
        _metric(2, "B", indices=["NDX"], change_pct=-1.0, sma200=99.0, last_close=98.0, new_low=True),
        _metric(3, "C", indices=["SSE50"], change_pct=2.0, sma200=99.0, last_close=110.0, vol_ratio=3.0),
    ]
    rows = aggregate_by_index(ms, [("NDX", "Nasdaq"), ("SP500", "S&P"), ("SSE50", "SSE"), ("DJI", "Dow")])
    by_code = {r["code"]: r for r in rows}
    assert by_code["NDX"]["n"] == 2
    assert by_code["SP500"]["n"] == 1
    assert by_code["SSE50"]["n"] == 1
    assert by_code["DJI"]["n"] == 0
    assert by_code["DJI"]["pct_above_sma200"] is None    # empty bucket
    assert by_code["NDX"]["new_52w_lows"] == 1
    assert by_code["SSE50"]["volume_spikes_count"] == 1


def test_aggregate_by_sector_sorted_by_avg_change():
    ms = [
        _metric(1, "A", sector="Tech", change_pct=2.0),
        _metric(2, "B", sector="Tech", change_pct=1.0),
        _metric(3, "C", sector="Energy", change_pct=-1.5),
        _metric(4, "D", sector="Finance", change_pct=0.5),
    ]
    rows = aggregate_by_sector(ms)
    assert [r["sector"] for r in rows] == ["Tech", "Finance", "Energy"]
    assert rows[0]["n_stocks"] == 2
    assert rows[0]["avg_change_pct"] == 1.5
