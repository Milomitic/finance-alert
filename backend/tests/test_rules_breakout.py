"""Tests for BreakoutRule."""
import pandas as pd

from app.rules.breakout_rules import BreakoutRule


def _ohlcv_close(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [0] * n,
    })


def test_breakout_true_when_close_exceeds_period_max_excluding_today() -> None:
    rule = BreakoutRule()
    closes = [100.0] * 20 + [105.0]
    df = _ohlcv_close(closes)
    assert rule.evaluate(df, {"period": 20}) is True


def test_breakout_false_when_close_below_or_equal_to_period_max() -> None:
    rule = BreakoutRule()
    closes = [100.0] * 20 + [100.0]
    df = _ohlcv_close(closes)
    assert rule.evaluate(df, {"period": 20}) is False


def test_breakout_kind_and_defaults() -> None:
    r = BreakoutRule()
    assert r.kind == "breakout"
    assert r.default_params == {"period": 20}


def test_breakout_snapshot_has_prior_max() -> None:
    rule = BreakoutRule()
    closes = [100.0] * 20 + [105.0]
    df = _ohlcv_close(closes)
    snap = rule.snapshot(df, {"period": 20})
    assert snap["prior_max"] == 100.0
    assert snap["close"] == 105.0
    assert snap["period"] == 20
