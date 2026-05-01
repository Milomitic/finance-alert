"""Tests for Wilder's Relative Strength Index."""
import math

import pandas as pd
import pytest

from app.indicators.rsi import rsi


def test_rsi_constant_price_yields_nan_or_50() -> None:
    """If price never changes, gain=loss=0 -> rs is 0/0=NaN; final value should be NaN."""
    s = pd.Series([100.0] * 30)
    result = rsi(s, 14)
    # All deltas are 0 so avg_gain and avg_loss are both 0; rs = 0/0 = NaN.
    assert math.isnan(result.iloc[-1])


def test_rsi_steadily_increasing_approaches_100() -> None:
    """With monotonically increasing prices, RSI should be very high (>90)."""
    s = pd.Series([float(i) for i in range(1, 51)])  # 1..50
    result = rsi(s, 14)
    # After warmup, RSI should be near 100 (all gains, no losses)
    assert result.iloc[-1] > 90.0


def test_rsi_steadily_decreasing_approaches_0() -> None:
    s = pd.Series([float(i) for i in range(50, 0, -1)])  # 50..1
    result = rsi(s, 14)
    assert result.iloc[-1] < 10.0


def test_rsi_warmup_returns_nan() -> None:
    """First `period` values should be NaN since avg_gain/avg_loss need history."""
    s = pd.Series([100.0, 102.0, 101.0])
    result = rsi(s, 14)
    # Less than 14 values -> all NaN
    assert all(math.isnan(v) for v in result.iloc[:1])
