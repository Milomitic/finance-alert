"""Tests for Exponential Moving Average."""
import pandas as pd
import pytest

from app.indicators.ema import ema


def test_ema_starts_from_first_value() -> None:
    """With adjust=False, EMA initializes to first value (no NaN at start)."""
    s = pd.Series([10.0, 11.0, 12.0])
    result = ema(s, 3)
    assert result.iloc[0] == pytest.approx(10.0)


def test_ema_period_3_known_recursion() -> None:
    """alpha = 2/(period+1) = 0.5 for period=3.
    EMA[t] = alpha*close[t] + (1-alpha)*EMA[t-1].
    """
    s = pd.Series([10.0, 12.0, 14.0])
    result = ema(s, 3)
    # EMA[0] = 10
    # EMA[1] = 0.5*12 + 0.5*10 = 11
    # EMA[2] = 0.5*14 + 0.5*11 = 12.5
    assert result.iloc[0] == pytest.approx(10.0)
    assert result.iloc[1] == pytest.approx(11.0)
    assert result.iloc[2] == pytest.approx(12.5)
