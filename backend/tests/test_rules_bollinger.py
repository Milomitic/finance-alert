"""Tests for Bollinger squeeze and breakout rules."""
import pandas as pd

from app.rules.bollinger_rules import BollingerBreakoutRule, BollingerSqueezeRule


def test_bollinger_squeeze_kind_defaults() -> None:
    r = BollingerSqueezeRule()
    assert r.kind == "bollinger_squeeze"
    assert r.default_params == {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}


def test_bollinger_breakout_kind_defaults() -> None:
    r = BollingerBreakoutRule()
    assert r.kind == "bollinger_breakout"
    assert r.default_params == {"period": 20, "k": 2.0, "direction": "either"}


def test_bollinger_squeeze_true_when_width_in_low_percentile() -> None:
    early = [100.0 + (i % 2) * 10.0 for i in range(80)]
    late = [105.0] * 20
    closes = early + late
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerSqueezeRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}) is True


def test_bollinger_squeeze_false_when_width_normal() -> None:
    closes = [100.0 + (i % 2) * 5.0 for i in range(80)]
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerSqueezeRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}) is False


def test_bollinger_breakout_upper_true_when_close_above_upper() -> None:
    closes = [100.0] * 30 + [200.0]
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerBreakoutRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "direction": "upper"}) is True


def test_bollinger_breakout_lower_true_when_close_below_lower() -> None:
    closes = [100.0] * 30 + [10.0]
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerBreakoutRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "direction": "lower"}) is True


def test_bollinger_breakout_either_matches_any_side() -> None:
    closes = [100.0] * 30 + [200.0]
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerBreakoutRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "direction": "either"}) is True
