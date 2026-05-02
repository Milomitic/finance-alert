"""Tests for MACD cross rules."""
import pandas as pd

from app.rules.macd_rules import MacdBearishCrossRule, MacdBullishCrossRule


def test_macd_bullish_cross_kind() -> None:
    assert MacdBullishCrossRule().kind == "macd_bullish_cross"
    assert MacdBearishCrossRule().kind == "macd_bearish_cross"


def test_macd_bullish_cross_defaults() -> None:
    assert MacdBullishCrossRule().default_params == {"fast": 12, "slow": 26, "signal": 9}


def test_macd_bullish_cross_true_when_line_crosses_above_signal() -> None:
    s = [100.0 - i * 1.0 for i in range(50)] + [50.0 + i * 5.0 for i in range(15)]
    df = pd.DataFrame({"close": s, "open": s, "high": s, "low": s, "volume": [0] * len(s)})
    rule = MacdBullishCrossRule()
    crossed = False
    for end in range(55, len(s) + 1):
        sub = df.iloc[:end]
        if rule.evaluate(sub, {}):
            crossed = True
            break
    assert crossed


def test_macd_bearish_cross_true_when_line_crosses_below_signal() -> None:
    s = [100.0 + i * 1.0 for i in range(50)] + [150.0 - i * 5.0 for i in range(15)]
    df = pd.DataFrame({"close": s, "open": s, "high": s, "low": s, "volume": [0] * len(s)})
    rule = MacdBearishCrossRule()
    crossed = False
    for end in range(55, len(s) + 1):
        sub = df.iloc[:end]
        if rule.evaluate(sub, {}):
            crossed = True
            break
    assert crossed


def test_macd_snapshot_has_line_signal_hist() -> None:
    s = [100.0 + i * 0.5 for i in range(60)]
    df = pd.DataFrame({"close": s, "open": s, "high": s, "low": s, "volume": [0] * len(s)})
    snap = MacdBullishCrossRule().snapshot(df, {})
    assert "line" in snap and "signal" in snap and "hist" in snap
