"""Loader for the generated signal-calibration artifact (Probabilità source).

`app/data/signal_calibration.json` is produced by
`app.scripts.signal_detector_outcomes --emit-map`: per-detector ABSOLUTE
forward hit-rates (the base rate for Probabilità) + optional per-factor
adjustment points. This module reads it once (cached) and turns a detector +
its factors into a Probabilità via `base.probability_from_factors`.

Degrades gracefully: unknown detector → neutral 50; missing artifact → an
all-neutral map, so the signal engine never crashes if the file hasn't been
generated yet (e.g. a fresh checkout before the harness is run).
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "signal_calibration.json"


class CalibrationMap:
    """Wraps the calibration payload. Construct from a dict (tests) or via
    `load_calibration(path)`."""

    def __init__(self, data: dict) -> None:
        self._detectors: dict = data.get("detectors", {}) or {}
        self._adj: dict = data.get("factor_adjustments", {}) or {}
        self.version = data.get("version")

    def base_rate(self, detector: str, default: float = 50.0) -> float:
        rec = self._detectors.get(detector)
        if not rec:
            return default
        return float(rec.get("base_rate", default))

    def horizon_days(self, detector: str) -> int | None:
        rec = self._detectors.get(detector)
        return int(rec["horizon_days"]) if rec and "horizon_days" in rec else None

    def adj_table(self, detector: str) -> dict[str, list[tuple[float, float]]]:
        """Per-factor adjustment points for `detector`, keyed by the BARE factor
        key (the detector prefix in the JSON is stripped), values as tuples."""
        prefix = detector + "."
        out: dict[str, list[tuple[float, float]]] = {}
        for qualified, pts in self._adj.items():
            if qualified.startswith(prefix):
                key = qualified[len(prefix):]
                out[key] = [(float(a), float(b)) for a, b in pts]
        return out

    def skill(self, detector: str) -> float | None:
        """Market-neutral hit-rate (`mkt_neutral_hit`) — the BETA-STRIPPED view.
        Unlike base_rate (absolute close-to-close hit, which credits market
        beta), this isolates the detector's edge over the universe drift. None
        when the artifact lacks it (degrade to neutral display)."""
        rec = self._detectors.get(detector)
        if not rec or "mkt_neutral_hit" not in rec:
            return None
        return float(rec["mkt_neutral_hit"])

    def edge_pct(self, detector: str) -> float | None:
        """Realised market-neutral forward edge (%) for the detector, or None."""
        rec = self._detectors.get(detector)
        if not rec or "mkt_neutral_edge_pct" not in rec:
            return None
        return float(rec["mkt_neutral_edge_pct"])

    def sample_n(self, detector: str) -> int | None:
        """Calibration sample size (number of historical signals), or None."""
        rec = self._detectors.get(detector)
        if not rec or "n" not in rec:
            return None
        return int(rec["n"])

    def quality_tag(self, detector: str) -> str | None:
        """Honesty tag from the calibration evidence (None for unknown detector).
        Keys off the BETA-STRIPPED skill (market-neutral hit), NOT the absolute
        base rate — a high base rate that is pure market beta (e.g.
        high52_momentum: base 55 but skill 48) must NOT read as edge:
          - "negative": realised market-neutral edge < -0.3% (anti-predictive).
          - "edge":     market-neutral skill > 52 (a genuine, beta-stripped edge).
          - "coinflip": everything else (skill ~50 → no real edge).
        Given single-name technicals are near coin-flips, most → "coinflip"."""
        rec = self._detectors.get(detector)
        if not rec:
            return None
        edge = rec.get("mkt_neutral_edge_pct")
        edge = float(edge) if edge is not None else 0.0
        if edge < -0.3:
            return "negative"
        sk = self.skill(detector)
        ref = sk if sk is not None else float(rec.get("base_rate", 50.0))
        return "edge" if ref > 52.0 else "coinflip"

    def detector_stats(self, detector: str) -> dict | None:
        """Bundle of the per-detector calibration facts for display, or None."""
        rec = self._detectors.get(detector)
        if not rec:
            return None
        return {
            "base_rate": float(rec.get("base_rate", 50.0)),
            "skill": self.skill(detector),
            "edge_pct": self.edge_pct(detector),
            "n": self.sample_n(detector),
            "horizon_days": self.horizon_days(detector),
            "tag": self.quality_tag(detector),
        }

    def all_detector_stats(self) -> dict[str, dict]:
        """Per-detector stats keyed by detector name (for the calibration API)."""
        return {name: self.detector_stats(name) for name in self._detectors}

    def probability(self, detector: str, factors: dict[str, float]) -> int:
        # Local import avoids a circular import at module load (base imports
        # nothing from here, but keep the dependency one-directional + lazy).
        from app.signals.detectors.base import probability_from_factors

        return probability_from_factors(
            self.base_rate(detector), factors, self.adj_table(detector)
        )


def load_calibration(path: Path = _DEFAULT_PATH) -> CalibrationMap:
    """Read the artifact at `path`; an absent/unreadable file → neutral map."""
    try:
        if not path.exists():
            return CalibrationMap({})
        return CalibrationMap(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return CalibrationMap({})


_cache: CalibrationMap | None = None


def get_calibration() -> CalibrationMap:
    """Process-wide singleton (loaded once from the default path)."""
    global _cache
    if _cache is None:
        _cache = load_calibration()
    return _cache


def reset_cache() -> None:
    """For tests / after regenerating the artifact."""
    global _cache
    _cache = None
