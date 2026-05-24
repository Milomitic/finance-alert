"""Trend-maturity factor + trend_age in the signal context."""
import pandas as pd

from app.signals.context import build_context
from app.signals.detectors.base import trend_maturity_factor


def _df(prices):
    d = pd.date_range("2025-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({
        "date": [x.strftime("%Y-%m-%d") for x in d],
        "open": [float(p) for p in prices],
        "high": [float(p) + 1 for p in prices],
        "low": [float(p) - 1 for p in prices],
        "close": [float(p) for p in prices],
        "volume": [1000.0] * len(prices),
    })


def test_trend_maturity_factor_shape():
    assert trend_maturity_factor(None) == 0.6
    assert trend_maturity_factor(30) == 0.5
    assert trend_maturity_factor(90) == 0.7
    assert trend_maturity_factor(180) == 1.0
    assert trend_maturity_factor(400) == 0.35
    # mature trend penalized vs mid-life (the backtest finding)
    assert trend_maturity_factor(400) < trend_maturity_factor(180)
    assert trend_maturity_factor(30) < trend_maturity_factor(180)


def test_trend_age_none_when_short_history():
    assert build_context(_df([100] * 150)).trend_age is None


def test_trend_age_positive_in_long_uptrend():
    ctx = build_context(_df([100 + i for i in range(300)]))
    assert ctx.trend_age is not None and ctx.trend_age > 0
