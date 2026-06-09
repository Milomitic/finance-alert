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
        # base outside [48,52] + positive market-neutral edge → genuine "edge"
        "oversold_reversal": {"base_rate": 56, "horizon_days": 21, "n": 9000,
                              "mkt_neutral_hit": 54.0, "mkt_neutral_edge_pct": 0.5},
        # base in [48,52] + ~0 edge → "coinflip"
        "gap_and_go": {"base_rate": 49, "horizon_days": 5, "n": 5000,
                       "mkt_neutral_hit": 49.5, "mkt_neutral_edge_pct": -0.1},
        # negative market-neutral edge → "negative" (anti-predictive)
        "structure_break": {"base_rate": 45, "horizon_days": 63, "n": 1278,
                            "mkt_neutral_hit": 46.6, "mkt_neutral_edge_pct": -1.46},
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


class TestCalibrationQuality:
    """Beta-stripped skill + honesty tags (Engine Quality v1, A+B)."""

    def test_skill_is_market_neutral_hit(self):
        assert CalibrationMap(DATA).skill("oversold_reversal") == 54.0

    def test_skill_unknown_detector_is_none(self):
        assert CalibrationMap(DATA).skill("nope") is None

    def test_edge_pct(self):
        assert CalibrationMap(DATA).edge_pct("structure_break") == -1.46

    def test_sample_n(self):
        assert CalibrationMap(DATA).sample_n("gap_and_go") == 5000

    def test_quality_tag_negative_edge(self):
        assert CalibrationMap(DATA).quality_tag("structure_break") == "negative"

    def test_quality_tag_coinflip(self):
        assert CalibrationMap(DATA).quality_tag("gap_and_go") == "coinflip"

    def test_quality_tag_genuine_edge(self):
        assert CalibrationMap(DATA).quality_tag("oversold_reversal") == "edge"

    def test_quality_tag_unknown_detector_is_none(self):
        assert CalibrationMap(DATA).quality_tag("nope") is None

    def test_quality_tag_keys_off_skill_not_base_rate(self):
        # high52_momentum-like: high ABSOLUTE base (55) but market-neutral skill
        # is sub-50 (pure up-tape beta) → must be "coinflip", NOT "edge".
        m = CalibrationMap({"detectors": {
            "beta_trap": {"base_rate": 55, "mkt_neutral_hit": 48.1,
                          "mkt_neutral_edge_pct": -0.29, "n": 2325, "horizon_days": 63},
        }})
        assert m.quality_tag("beta_trap") == "coinflip"

    def test_detector_stats_bundles_all_fields(self):
        s = CalibrationMap(DATA).detector_stats("structure_break")
        assert s == {
            "base_rate": 45.0, "skill": 46.6, "edge_pct": -1.46,
            "n": 1278, "horizon_days": 63, "tag": "negative",
        }

    def test_detector_stats_unknown_is_none(self):
        assert CalibrationMap(DATA).detector_stats("nope") is None

    def test_all_detector_stats_keyed_by_name(self):
        allstats = CalibrationMap(DATA).all_detector_stats()
        assert set(allstats) == {"oversold_reversal", "gap_and_go", "structure_break"}
        assert allstats["gap_and_go"]["tag"] == "coinflip"


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
