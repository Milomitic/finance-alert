"""Tests for Wilder's ATR."""
import pandas as pd

from app.indicators.atr import atr


def _ohlcv(highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [0] * len(closes),
    })


def test_atr_constant_range_yields_constant_value() -> None:
    n = 30
    highs = [101.0] * n
    lows = [100.0] * n
    closes = [100.5] * n
    df = _ohlcv(highs, lows, closes)
    result = atr(df, period=14)
    assert abs(result.iloc[-1] - 1.0) < 1e-9


def test_atr_increasing_volatility_increases() -> None:
    n = 30
    highs = [100.0 + i * 0.5 for i in range(n)]
    lows = [99.0 - i * 0.5 for i in range(n)]
    closes = [99.5 + i * 0.0 for i in range(n)]
    df = _ohlcv(highs, lows, closes)
    result = atr(df, period=14)
    assert result.iloc[-1] > 5.0


def test_atr_warmup_returns_nan() -> None:
    df = _ohlcv([101.0, 102.0], [99.0, 100.0], [100.0, 101.0])
    result = atr(df, period=14)
    assert pd.isna(result.iloc[0])
