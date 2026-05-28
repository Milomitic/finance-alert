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
