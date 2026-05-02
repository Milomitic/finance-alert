"""Tests for Bollinger Bands."""
import pandas as pd

from app.indicators.bb import bb_width, bollinger


def test_bollinger_returns_three_series_same_length() -> None:
    s = pd.Series([100.0 + i * 0.5 for i in range(40)])
    upper, middle, lower = bollinger(s, period=20, k=2.0)
    assert len(upper) == len(middle) == len(lower) == 40


def test_bollinger_middle_equals_sma() -> None:
    s = pd.Series([float(v) for v in range(1, 31)])
    _u, middle, _l = bollinger(s, period=10, k=2.0)
    assert abs(middle.iloc[-1] - 25.5) < 1e-9


def test_bollinger_upper_above_lower_with_volatility() -> None:
    s = pd.Series([100.0, 110.0] * 25)
    upper, _m, lower = bollinger(s, period=20, k=2.0)
    assert upper.iloc[-1] > lower.iloc[-1]


def test_bb_width_positive_with_volatility() -> None:
    s = pd.Series([100.0, 110.0] * 25)
    w = bb_width(s, period=20, k=2.0)
    assert w.iloc[-1] > 0
