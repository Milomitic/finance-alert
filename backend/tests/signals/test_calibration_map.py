"""Tests for the calibration-map loader (Phase B1c).

CalibrationMap wraps the generated signal_calibration.json: detector base rates
(absolute hit-rate → Probabilità base) + optional per-factor adjustment points.
It must degrade gracefully — an unknown detector/factor is neutral (50 / no
adjustment), and a missing file yields an all-neutral map (so the app never
crashes if the artifact hasn't been generated).
"""
from pathlib import Path

from app.signals.calibration_map import CalibrationMap, load_calibration

DATA = {
    "version": "test",
    "detectors": {
        "oversold_reversal": {"base_rate": 56, "horizon_days": 21, "n": 9000},
        "gap_and_go": {"base_rate": 49, "horizon_days": 5, "n": 5000},
    },
    "factor_adjustments": {
        "oversold_reversal.rsi_extremity": [[0.0, 0.0], [0.3, 6.0]],
    },
}


class TestCalibrationMap:
    def test_known_base_rate(self):
        assert CalibrationMap(DATA).base_rate("oversold_reversal") == 56.0

    def test_unknown_detector_defaults_to_50(self):
        assert CalibrationMap(DATA).base_rate("nope") == 50.0

    def test_unknown_detector_custom_default(self):
        assert CalibrationMap(DATA).base_rate("nope", default=42.0) == 42.0

    def test_horizon_days(self):
        assert CalibrationMap(DATA).horizon_days("gap_and_go") == 5

    def test_adj_table_strips_detector_prefix_and_tuples(self):
        tbl = CalibrationMap(DATA).adj_table("oversold_reversal")
        assert tbl == {"rsi_extremity": [(0.0, 0.0), (0.3, 6.0)]}

    def test_adj_table_empty_for_detector_without_adjustments(self):
        assert CalibrationMap(DATA).adj_table("gap_and_go") == {}

    def test_probability_applies_base_plus_adjustment(self):
        # base 56 + interp(0.3)=+6 → 62
        assert CalibrationMap(DATA).probability(
            "oversold_reversal", {"rsi_extremity": 0.3}) == 62

    def test_probability_no_adjustment(self):
        assert CalibrationMap(DATA).probability("gap_and_go", {"gap_size": 0.5}) == 49

    def test_probability_unknown_detector_is_neutral(self):
        assert CalibrationMap(DATA).probability("mystery", {"x": 0.9}) == 50


class TestLoadCalibration:
    def test_missing_file_yields_neutral_map(self):
        m = load_calibration(Path("does/not/exist.json"))
        assert m.base_rate("anything") == 50.0
        assert m.probability("anything", {"x": 1.0}) == 50

    def test_loads_real_file_if_present(self, tmp_path):
        import json
        p = tmp_path / "cal.json"
        p.write_text(json.dumps(DATA), encoding="utf-8")
        m = load_calibration(p)
        assert m.base_rate("oversold_reversal") == 56.0
