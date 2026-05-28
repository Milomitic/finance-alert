"""Tests for the Probabilità math (Phase B1b) — pure, no file I/O.

probability_from_factors computes a signal's probability "di accadimento" as the
detector's historical base rate plus a bounded sum of per-factor adjustments,
clamped to a sane band. interp_adjustment is the piecewise-linear lookup of a
factor's raw value into its (raw → adjustment) calibration points.
"""
from app.signals.detectors.base import interp_adjustment, probability_from_factors


class TestInterpAdjustment:
    def test_empty_points_returns_zero(self):
        assert interp_adjustment(0.5, []) == 0.0

    def test_below_first_point_returns_first_adj(self):
        assert interp_adjustment(0.0, [(0.1, 3.0), (0.3, 6.0)]) == 3.0

    def test_above_last_point_returns_last_adj(self):
        assert interp_adjustment(0.9, [(0.1, 3.0), (0.3, 6.0)]) == 6.0

    def test_exact_point(self):
        assert interp_adjustment(0.3, [(0.1, 3.0), (0.3, 6.0)]) == 6.0

    def test_midpoint_linear(self):
        # 0.2 halfway between 0.1(3.0) and 0.3(6.0) → 4.5
        assert abs(interp_adjustment(0.2, [(0.1, 3.0), (0.3, 6.0)]) - 4.5) < 1e-9

    def test_unsorted_points_handled(self):
        assert abs(interp_adjustment(0.2, [(0.3, 6.0), (0.1, 3.0)]) - 4.5) < 1e-9


class TestProbabilityFromFactors:
    def test_no_adjustments_returns_base(self):
        assert probability_from_factors(56.0, {"x": 0.5}, {}) == 56

    def test_single_factor_adjustment_applied(self):
        adj = {"rsi_extremity": [(0.0, 0.0), (0.3, 6.0)]}
        assert probability_from_factors(52.0, {"rsi_extremity": 0.3}, adj) == 58

    def test_total_adjustment_clamped(self):
        adj = {"a": [(0.0, 20.0)], "b": [(0.0, 20.0)]}
        # each → +20, sum 40, clamp to +8 → 50+8
        assert probability_from_factors(50.0, {"a": 0.5, "b": 0.5}, adj,
                                        max_total_adj=8.0) == 58

    def test_result_clamped_to_ceil(self):
        assert probability_from_factors(94.0, {"a": 0.5}, {"a": [(0.0, 20.0)]},
                                        ceil=95.0) == 95

    def test_result_clamped_to_floor(self):
        assert probability_from_factors(6.0, {"a": 0.5}, {"a": [(0.0, -20.0)]},
                                        floor=5.0) == 5

    def test_unknown_factor_ignored(self):
        assert probability_from_factors(50.0, {"unknown": 0.9},
                                        {"known": [(0.0, 5.0)]}) == 50

    def test_negative_adjustment_lowers_probability(self):
        # a mean-reverting factor can carry a negative adjustment
        adj = {"gap_size": [(0.02, 0.0), (0.20, -6.0)]}
        assert probability_from_factors(50.0, {"gap_size": 0.20}, adj) == 44
