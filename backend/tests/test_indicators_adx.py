"""Tests for ADX + ±DI."""
import pandas as pd

from app.indicators.adx import adx


def _ohlcv(highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [0] * len(closes),
    })


def test_adx_strong_uptrend_high_adx_plus_di_dominates() -> None:
    n = 60
    highs = [100.0 + i * 1.0 for i in range(n)]
    lows = [99.0 + i * 1.0 for i in range(n)]
    closes = [99.5 + i * 1.0 for i in range(n)]
    df = _ohlcv(highs, lows, closes)
    a, p, m = adx(df, period=14)
    assert a.iloc[-1] > 25.0
    assert p.iloc[-1] > m.iloc[-1]


def test_adx_strong_downtrend_minus_di_dominates() -> None:
    n = 60
    highs = [200.0 - i * 1.0 for i in range(n)]
    lows = [199.0 - i * 1.0 for i in range(n)]
    closes = [199.5 - i * 1.0 for i in range(n)]
    df = _ohlcv(highs, lows, closes)
    a, p, m = adx(df, period=14)
    assert a.iloc[-1] > 25.0
    assert m.iloc[-1] > p.iloc[-1]


def test_adx_returns_three_same_length_series() -> None:
    n = 30
    df = _ohlcv([101.0] * n, [99.0] * n, [100.0] * n)
    a, p, m = adx(df, period=14)
    assert len(a) == len(p) == len(m) == n
