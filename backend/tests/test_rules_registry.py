"""Tests for rule registry."""
import pytest

from app.rules.registry import RULES, get_rule
from app.rules.rsi_rules import RsiOversoldRule, RsiOverboughtRule
from app.rules.cross_rules import GoldenCrossRule, DeathCrossRule


def test_registry_contains_all_4_kinds() -> None:
    assert set(RULES.keys()) == {"rsi_oversold", "rsi_overbought", "golden_cross", "death_cross"}


def test_get_rule_returns_correct_class() -> None:
    assert isinstance(get_rule("rsi_oversold"), RsiOversoldRule)
    assert isinstance(get_rule("rsi_overbought"), RsiOverboughtRule)
    assert isinstance(get_rule("golden_cross"), GoldenCrossRule)
    assert isinstance(get_rule("death_cross"), DeathCrossRule)


def test_get_rule_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_rule("nonexistent_rule")
