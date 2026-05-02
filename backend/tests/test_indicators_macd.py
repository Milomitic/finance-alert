"""Tests for MACD indicator."""
import math

import pandas as pd

from app.indicators.macd import macd


def test_macd_returns_three_series_same_length() -> None:
    s = pd.Series([100.0 + i * 0.5 for i in range(60)])
    line, signal, hist = macd(s)
    assert len(line) == len(signal) == len(hist) == 60


def test_macd_uptrend_line_above_signal_eventually() -> None:
    """In a steady uptrend, MACD line crosses above signal and stays positive."""
    s = pd.Series([100.0 + i * 1.0 for i in range(80)])
    line, signal, hist = macd(s)
    assert line.iloc[-1] > signal.iloc[-1]
    assert hist.iloc[-1] > 0


def test_macd_downtrend_line_below_signal() -> None:
    s = pd.Series([200.0 - i * 1.0 for i in range(80)])
    line, signal, _hist = macd(s)
    assert line.iloc[-1] < signal.iloc[-1]


def test_macd_warmup_yields_finite_after_slow_period() -> None:
    s = pd.Series([100.0 + i * 0.1 for i in range(60)])
    line, signal, hist = macd(s, fast=12, slow=26, signal=9)
    assert not math.isnan(line.iloc[50])
    assert not math.isnan(signal.iloc[50])
    assert not math.isnan(hist.iloc[50])
