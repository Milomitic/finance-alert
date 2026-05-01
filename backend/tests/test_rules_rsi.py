"""Tests for RSI rules."""
import pandas as pd

from app.rules.rsi_rules import RsiOverboughtRule, RsiOversoldRule


def _series_for_rsi(target_rsi: float, length: int = 30) -> pd.Series:
    """Build a price series that will produce ~target_rsi at the last bar."""
    if target_rsi < 50:
        # heavily declining
        return pd.Series([100.0 - i * 0.5 for i in range(length)])
    else:
        # heavily rising
        return pd.Series([100.0 + i * 0.5 for i in range(length)])


def test_rsi_oversold_returns_true_when_rsi_below_threshold() -> None:
    rule = RsiOversoldRule()
    ohlcv = pd.DataFrame({"close": _series_for_rsi(20.0)})
    assert rule.evaluate(ohlcv, {"period": 14, "threshold": 30}) is True


def test_rsi_oversold_returns_false_when_rsi_above_threshold() -> None:
    rule = RsiOversoldRule()
    ohlcv = pd.DataFrame({"close": _series_for_rsi(80.0)})
    assert rule.evaluate(ohlcv, {"period": 14, "threshold": 30}) is False


def test_rsi_overbought_returns_true_when_rsi_above_threshold() -> None:
    rule = RsiOverboughtRule()
    ohlcv = pd.DataFrame({"close": _series_for_rsi(80.0)})
    assert rule.evaluate(ohlcv, {"period": 14, "threshold": 70}) is True


def test_rsi_overbought_returns_false_when_rsi_below_threshold() -> None:
    rule = RsiOverboughtRule()
    ohlcv = pd.DataFrame({"close": _series_for_rsi(20.0)})
    assert rule.evaluate(ohlcv, {"period": 14, "threshold": 70}) is False


def test_rsi_rule_kind_attribute() -> None:
    assert RsiOversoldRule().kind == "rsi_oversold"
    assert RsiOverboughtRule().kind == "rsi_overbought"


def test_rsi_rule_default_params() -> None:
    assert RsiOversoldRule().default_params == {"period": 14, "threshold": 30}
    assert RsiOverboughtRule().default_params == {"period": 14, "threshold": 70}


def test_rsi_oversold_snapshot_includes_rsi_value() -> None:
    rule = RsiOversoldRule()
    ohlcv = pd.DataFrame({"close": _series_for_rsi(20.0)})
    snap = rule.snapshot(ohlcv, {"period": 14, "threshold": 30})
    assert "rsi" in snap and 0.0 <= snap["rsi"] <= 100.0
    assert snap["period"] == 14
    assert snap["threshold"] == 30
