"""Tests for Simple Moving Average."""
import math

import pandas as pd
import pytest

from app.indicators.sma import sma


def test_sma_period_3_on_known_series() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    result = sma(s, 3)
    # First 2 values are NaN (warmup); from index 2 onward: avg of last 3
    assert math.isnan(result.iloc[0])
    assert math.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)  # (1+2+3)/3
    assert result.iloc[3] == pytest.approx(3.0)
    assert result.iloc[4] == pytest.approx(4.0)
    assert result.iloc[5] == pytest.approx(5.0)


def test_sma_returns_nan_in_warmup() -> None:
    s = pd.Series([10.0, 20.0])
    result = sma(s, 5)
    assert all(math.isnan(v) for v in result)
