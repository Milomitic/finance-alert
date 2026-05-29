"""Unit tests for the retune OOS gate — the iron rule made executable.

`passes_oos_gate(baseline, candidate, *, min_rel_improvement, lower_is_better)`
encodes the score-retune loop's standing discipline: REJECT a candidate unless
it is CLEARLY better OUT-OF-SAMPLE. These tests pin the four corners of that
rule — improves → True, flat/worse → False, NaN-safe, and the degenerate
zero/sign-change regime — so the gate can't silently drift toward "accept
anything" (the exact mistake the rule exists to prevent).

Pure math, no I/O, no DB.
"""
import math

from app.scripts.retune import passes_oos_gate


class TestHigherIsBetter:
    """Default orientation (e.g. rank-IC): a larger metric is better."""

    def test_clear_improvement_passes(self):
        # +10% on a +0.05 baseline, asking for +5% → PASS.
        assert passes_oos_gate(0.0500, 0.0550, min_rel_improvement=0.05) is True

    def test_exactly_at_threshold_passes(self):
        # candidate == baseline * (1 + rel) → boundary is inclusive.
        assert passes_oos_gate(0.0500, 0.0525, min_rel_improvement=0.05) is True

    def test_flat_fails(self):
        # No change at all → not "clearly better" → REJECT.
        assert passes_oos_gate(0.0500, 0.0500, min_rel_improvement=0.05) is False

    def test_worse_fails(self):
        assert passes_oos_gate(0.0500, 0.0400, min_rel_improvement=0.05) is False

    def test_tiny_improvement_below_bar_fails(self):
        # +2% when the bar is +5% → not clearly better.
        assert passes_oos_gate(0.0500, 0.0510, min_rel_improvement=0.05) is False


class TestLowerIsBetter:
    """Brier-style metrics: a smaller metric is better."""

    def test_clear_improvement_passes(self):
        # Brier 0.250 → 0.230 is a ~8% relative drop; bar 5% → PASS.
        assert passes_oos_gate(
            0.250, 0.230, min_rel_improvement=0.05, lower_is_better=True
        ) is True

    def test_flat_fails(self):
        assert passes_oos_gate(
            0.250, 0.250, min_rel_improvement=0.05, lower_is_better=True
        ) is False

    def test_worse_higher_brier_fails(self):
        assert passes_oos_gate(
            0.250, 0.270, min_rel_improvement=0.05, lower_is_better=True
        ) is False

    def test_tiny_drop_below_bar_fails(self):
        # 0.250 → 0.245 is only 2% better; bar 5% → REJECT.
        assert passes_oos_gate(
            0.250, 0.245, min_rel_improvement=0.05, lower_is_better=True
        ) is False


class TestNaNAndInfSafety:
    """An unmeasurable result can NEVER be 'clearly better' → always FAIL."""

    def test_nan_baseline_fails(self):
        assert passes_oos_gate(
            float("nan"), 0.05, min_rel_improvement=0.05
        ) is False

    def test_nan_candidate_fails(self):
        assert passes_oos_gate(
            0.05, float("nan"), min_rel_improvement=0.05
        ) is False

    def test_both_nan_fails(self):
        assert passes_oos_gate(
            float("nan"), float("nan"), min_rel_improvement=0.05
        ) is False

    def test_inf_candidate_fails(self):
        assert passes_oos_gate(
            0.05, float("inf"), min_rel_improvement=0.05
        ) is False

    def test_neg_inf_baseline_fails(self):
        assert passes_oos_gate(
            float("-inf"), 0.05, min_rel_improvement=0.05
        ) is False


class TestDegenerateRatioRegime:
    """Where relative improvement lies (baseline ~0, or a sign change), the gate
    falls back to an ABSOLUTE-points bar AND requires the correct side of zero."""

    def test_zero_baseline_uses_absolute_bar_pass(self):
        # baseline 0.0, candidate +0.06, absolute bar 0.05 → PASS.
        assert passes_oos_gate(0.0, 0.06, min_rel_improvement=0.05) is True

    def test_zero_baseline_below_absolute_bar_fails(self):
        assert passes_oos_gate(0.0, 0.04, min_rel_improvement=0.05) is False

    def test_sign_change_negative_to_positive_needs_absolute_margin(self):
        # The momentum-pillar precedent: counter-predictive (−0.01) → positive.
        # A small positive that doesn't clear the absolute bar is still REJECTED.
        assert passes_oos_gate(-0.010, 0.020, min_rel_improvement=0.05) is False
        # …but a positive that DOES clear it (and is on the right side) passes.
        assert passes_oos_gate(-0.010, 0.045, min_rel_improvement=0.05) is True

    def test_positive_to_negative_fails(self):
        # Going from a positive IC to a negative one is never an improvement.
        assert passes_oos_gate(0.030, -0.010, min_rel_improvement=0.05) is False

    def test_both_negative_closer_to_zero_can_pass(self):
        # Higher-is-better with both negative: candidate closer to 0 by enough.
        # base=-0.040, required = -0.040*(1-0.05) = -0.038; -0.030 >= -0.038 → PASS.
        assert passes_oos_gate(-0.040, -0.030, min_rel_improvement=0.05) is True

    def test_both_negative_not_enough_fails(self):
        # -0.039 does NOT clear required -0.038 → still REJECT.
        assert passes_oos_gate(-0.040, -0.039, min_rel_improvement=0.05) is False


class TestMinRelImprovementHandling:
    def test_negative_bar_is_treated_as_absolute_value(self):
        # A negative bar must NOT invert the rule into 'accept anything'.
        # |−0.05| = 0.05, so this behaves exactly like the +0.05 bar.
        assert passes_oos_gate(0.0500, 0.0510, min_rel_improvement=-0.05) is False
        assert passes_oos_gate(0.0500, 0.0600, min_rel_improvement=-0.05) is True

    def test_zero_bar_requires_strict_non_decrease(self):
        # With a 0% bar, candidate must merely be >= baseline (higher-is-better).
        assert passes_oos_gate(0.0500, 0.0500, min_rel_improvement=0.0) is True
        assert passes_oos_gate(0.0500, 0.0499, min_rel_improvement=0.0) is False

    def test_large_bar_demands_large_improvement(self):
        # A 50% bar: +10% is nowhere near enough.
        assert passes_oos_gate(0.0500, 0.0550, min_rel_improvement=0.50) is False
        assert passes_oos_gate(0.0500, 0.0800, min_rel_improvement=0.50) is True


def test_returns_plain_bool():
    # The gate must return a real bool (used directly in assertions / JSON).
    out = passes_oos_gate(0.05, 0.06, min_rel_improvement=0.05)
    assert out is True or out is False
    assert isinstance(out, bool)
    assert not isinstance(out, float)
    assert not math.isnan(float(out))
