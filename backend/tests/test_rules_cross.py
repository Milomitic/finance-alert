"""Tests for Golden Cross / Death Cross rules."""
import pandas as pd

from app.rules.cross_rules import DeathCrossRule, GoldenCrossRule


def _build_cross_data(transition: bool, *, fast_above_slow: bool) -> pd.DataFrame:
    """Build a 250-row series that produces a golden or death cross at the LAST bar.

    transition=True: SMA(fast) crosses SMA(slow) at the last bar.
    fast_above_slow: True for golden cross direction (fast crosses up); False for death.
    """
    n = 250
    if fast_above_slow and transition:
        # Build a series where SMA(50) was below SMA(200) at index -2 and above at index -1
        values = [100.0] * 200 + [99.0] * 49 + [200.0]  # final spike pulls SMA50 above SMA200
        return pd.DataFrame({"close": values})
    if not fast_above_slow and transition:
        values = [100.0] * 200 + [101.0] * 49 + [50.0]  # final dip pulls SMA50 below SMA200
        return pd.DataFrame({"close": values})
    # No transition: flat series, both SMAs equal
    return pd.DataFrame({"close": [100.0] * n})


def test_golden_cross_detects_upward_transition() -> None:
    rule = GoldenCrossRule()
    df = _build_cross_data(transition=True, fast_above_slow=True)
    assert rule.evaluate(df, {"fast": 50, "slow": 200}) is True


def test_golden_cross_returns_false_when_no_transition() -> None:
    rule = GoldenCrossRule()
    df = _build_cross_data(transition=False, fast_above_slow=True)
    assert rule.evaluate(df, {"fast": 50, "slow": 200}) is False


def test_death_cross_detects_downward_transition() -> None:
    rule = DeathCrossRule()
    df = _build_cross_data(transition=True, fast_above_slow=False)
    assert rule.evaluate(df, {"fast": 50, "slow": 200}) is True


def test_death_cross_returns_false_when_no_transition() -> None:
    rule = DeathCrossRule()
    df = _build_cross_data(transition=False, fast_above_slow=False)
    assert rule.evaluate(df, {"fast": 50, "slow": 200}) is False


def test_cross_returns_false_with_insufficient_data() -> None:
    """Series shorter than `slow` period should return False (NaN handling)."""
    df = pd.DataFrame({"close": [100.0] * 50})
    assert GoldenCrossRule().evaluate(df, {"fast": 50, "slow": 200}) is False
    assert DeathCrossRule().evaluate(df, {"fast": 50, "slow": 200}) is False


def test_cross_rule_kind_and_default_params() -> None:
    assert GoldenCrossRule().kind == "golden_cross"
    assert DeathCrossRule().kind == "death_cross"
    assert GoldenCrossRule().default_params == {"fast": 50, "slow": 200}
    assert DeathCrossRule().default_params == {"fast": 50, "slow": 200}


def test_cross_snapshot_includes_sma_values() -> None:
    df = _build_cross_data(transition=True, fast_above_slow=True)
    snap = GoldenCrossRule().snapshot(df, {"fast": 50, "slow": 200})
    assert "fast_sma" in snap and "slow_sma" in snap
    assert snap["fast_period"] == 50 and snap["slow_period"] == 200
