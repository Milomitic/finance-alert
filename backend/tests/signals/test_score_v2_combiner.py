"""Tests for score_v2 — the arith + soft-min confidence combiner (Phase A).

The combiner's job is to kill "mediocrity laundering": today a saturated
context factor (e.g. expansion_strength=1.0) plus a binary alignment=1.0 can
drag a mediocre STRENGTH factor (tightness≈p50) through the weighted mean into
confidence 90+. score_v2 caps the result at (weakest strength factor + delta),
so a high score genuinely requires every strength factor to be individually
strong — while alignment / maturity stay as additive context that can lift but
never themselves manufacture a high score.
"""
from app.signals.detectors.base import score, score_v2


class TestScoreV2SoftMin:
    def test_softmin_caps_when_weakest_strength_is_mediocre(self):
        # The real DB pattern: tightness mediocre, expansion saturated, aligned.
        factors = {"tightness": 0.55, "expansion": 1.0, "alignment": 1.0}
        weights = {"tightness": 0.8, "expansion": 1.0, "alignment": 0.8}
        # arith ≈ 0.862, but min(strength)=0.55 → cap 0.67.
        result = score_v2(factors, weights, strength_keys={"tightness", "expansion"})
        assert result == 67

    def test_strong_factor_lifts_only_delta_above_weakest(self):
        factors = {"f1": 1.0, "f2": 0.70}
        weights = {"f1": 1.0, "f2": 1.0}
        # arith=0.85; weakest strength=0.70 → cap 0.82 binds.
        result = score_v2(factors, weights, strength_keys={"f1", "f2"})
        assert result == 82

    def test_alignment_excluded_from_min_not_punished_twice(self):
        # Misaligned (floor 0.4) must NOT drag the soft-min: its weakness is
        # already encoded in the floor and enters arith only.
        factors = {"strength_f": 0.85, "trend_alignment": 0.4}
        weights = {"strength_f": 1.0, "trend_alignment": 0.8}
        result = score_v2(factors, weights, strength_keys={"strength_f"})
        # arith=(0.85+0.32)/1.8=0.65; min(strength)=0.85 → cap 0.97 (non-binding).
        assert result == 65

    def test_true_monster_reaches_high_band(self):
        # All strength factors individually strong → high score (this is what
        # SHOULD reach the top, unlike mediocre confluence).
        factors = {"f1": 0.90, "f2": 0.88, "alignment": 1.0}
        weights = {"f1": 1.0, "f2": 1.0, "alignment": 0.6}
        result = score_v2(factors, weights, strength_keys={"f1", "f2"})
        assert result >= 88

    def test_guardrail_caps_at_99(self):
        # 99 is the top — reachable only when every factor is maxed; 100 never.
        factors = {"f1": 1.0, "f2": 1.0}
        weights = {"f1": 1.0, "f2": 1.0}
        assert score_v2(factors, weights, strength_keys={"f1", "f2"}) == 99

    def test_no_strength_keys_falls_back_to_weighted_mean(self):
        factors = {"a": 0.6, "b": 0.6}
        weights = {"a": 1.0, "b": 1.0}
        assert score_v2(factors, weights, strength_keys=set()) == 60

    def test_custom_delta_is_respected(self):
        factors = {"f1": 1.0, "f2": 0.60}
        weights = {"f1": 1.0, "f2": 1.0}
        # delta=0.05 → cap 0.65 (stricter than default 0.12 → 0.72).
        assert score_v2(factors, weights, strength_keys={"f1", "f2"}, delta=0.05) == 65


class TestLegacyScoreUnchanged:
    """Guard: the 17 production detectors still call the old score(); it must
    remain bit-identical while score_v2 is introduced alongside it."""

    def test_characterization_value(self):
        # num=1.1, den=1.5, raw=0.7333 > knee 0.72 → compressed to ~0.731.
        assert score({"x": 0.8, "y": 0.6}, {"x": 1.0, "y": 0.5}) == 73

    def test_below_knee_untouched(self):
        # raw=0.5 (below knee) passes straight through.
        assert score({"x": 0.5}, {"x": 1.0}) == 50
