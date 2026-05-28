"""Tests for the per-factor calibration curves (confidence redesign, Phase A).

These curves replace the one-size-fits-all soft01/clamp01 shaping. Each factor
is mapped onto a curve whose anchor points are placed at data-grounded raw
values (from the forward-outcome study), so a factor value only reaches the top
of its range when the underlying parameter is genuinely a "monster".
"""
import math

from app.signals.detectors.base import concave, log_saturate


# A representative anchor set: (raw@0.45, raw@0.75, raw@0.88, ceil).
ANCH = (0.05, 0.14, 0.30, 0.60)


class TestConcave:
    def test_zero_maps_to_zero(self):
        assert concave(0.0, ANCH) == 0.0

    def test_negative_clamps_to_zero(self):
        assert concave(-1.0, ANCH) == 0.0

    def test_hits_anchor_points_exactly(self):
        a45, a75, a88, _ceil = ANCH
        assert abs(concave(a45, ANCH) - 0.45) < 1e-6
        assert abs(concave(a75, ANCH) - 0.75) < 1e-6
        assert abs(concave(a88, ANCH) - 0.88) < 1e-6

    def test_monotonic_increasing(self):
        xs = [0.0, 0.02, 0.05, 0.09, 0.14, 0.22, 0.30, 0.45, 0.60, 1.0, 5.0, 100.0]
        ys = [concave(x, ANCH) for x in xs]
        assert all(ys[i] <= ys[i + 1] + 1e-12 for i in range(len(ys) - 1))

    def test_never_reaches_ceiling_value(self):
        # Asymptote at 0.99 — even an extreme reading stays strictly below it
        # (100 is unreachable; 99 only approached by genuine monsters).
        assert concave(1e9, ANCH) < 0.99
        assert concave(1e9, ANCH) > 0.88

    def test_ceiling_anchor_in_top_band(self):
        # At the `ceil` anchor (the "monster" level) the curve is past 0.88 and
        # climbing toward 0.99 — beyond it is reserved for the truly extreme.
        _a45, _a75, _a88, ceil = ANCH
        v = concave(ceil, ANCH)
        assert 0.88 < v < 0.99

    def test_midpoint_below_45_for_subthreshold(self):
        # A raw value half-way to the first anchor should score well under 0.45.
        assert concave(ANCH[0] / 2, ANCH) < 0.45


class TestLogSaturate:
    def test_zero_maps_to_zero(self):
        assert log_saturate(0.0, ceil=9.0) == 0.0

    def test_negative_clamps_to_zero(self):
        assert log_saturate(-2.0, ceil=9.0) == 0.0

    def test_hits_target_at_ceil(self):
        assert abs(log_saturate(9.0, ceil=9.0, target=0.85) - 0.85) < 1e-6

    def test_monotonic_increasing(self):
        xs = [0.0, 0.5, 1.0, 3.0, 6.0, 9.0, 15.0, 50.0]
        ys = [log_saturate(x, ceil=9.0) for x in xs]
        assert all(ys[i] <= ys[i + 1] + 1e-12 for i in range(len(ys) - 1))

    def test_bounded_by_one(self):
        assert log_saturate(1e6, ceil=9.0) <= 1.0

    def test_exceeds_target_past_ceil(self):
        # Beyond the ceil the curve keeps rising (toward 1.0) — a true monster
        # gets credit beyond the "strong" reference.
        assert log_saturate(20.0, ceil=9.0, target=0.85) > 0.85

    def test_concave_shape(self):
        # log-shaped: equal raw increments give diminishing curve increments.
        d1 = log_saturate(2.0, ceil=9.0) - log_saturate(1.0, ceil=9.0)
        d2 = log_saturate(9.0, ceil=9.0) - log_saturate(8.0, ceil=9.0)
        assert d1 > d2
