"""Tests for the Bollinger breakout rule.

The squeeze rule was retired in migration
`47c2035665bd_drop_bollinger_squeeze_rules`. The category produced too
many false positives in choppy regimes and overlapped conceptually with
the new mean-reversion rules (which trigger on tail-of-distribution
moves rather than width compression).
"""
import pandas as pd

from app.rules.bollinger_rules import BollingerBreakoutRule


def test_bollinger_breakout_kind_defaults() -> None:
    r = BollingerBreakoutRule()
    assert r.kind == "bollinger_breakout"
    assert r.default_params == {"period": 20, "k": 2.0, "direction": "either"}


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
