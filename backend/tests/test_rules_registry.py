"""Tests for rule registry."""
import pytest

from app.rules.cross_rules import DeathCrossRule, GoldenCrossRule
from app.rules.registry import RULES, get_rule
from app.rules.rsi_rules import RsiOverboughtRule, RsiOversoldRule


def test_registry_contains_all_4_kinds() -> None:
    # Original 4 kinds must still be present (registry now contains more)
    for kind in {"rsi_oversold", "rsi_overbought", "golden_cross", "death_cross"}:
        assert kind in RULES


def test_get_rule_returns_correct_class() -> None:
    assert isinstance(get_rule("rsi_oversold"), RsiOversoldRule)
    assert isinstance(get_rule("rsi_overbought"), RsiOverboughtRule)
    assert isinstance(get_rule("golden_cross"), GoldenCrossRule)
    assert isinstance(get_rule("death_cross"), DeathCrossRule)


def test_get_rule_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_rule("nonexistent_rule")


def test_registry_contains_all_3c_rules() -> None:
    from app.rules.registry import RULES
    expected = {
        "rsi_oversold", "rsi_overbought", "golden_cross", "death_cross",
        "volume_spike", "breakout",
        "macd_bullish_cross", "macd_bearish_cross",
        "bollinger_squeeze", "bollinger_breakout",
    }
    assert expected.issubset(set(RULES.keys()))
