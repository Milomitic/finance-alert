"""Detector performance explorer — read-only aggregation over `signal_outcomes`.

The outcome warehouse (`app/models/signal_outcome.py`) supports slices the UI
never exposed: hit-rate per detector × regime-at-signal × tone × strength band.
This service computes that whole cube in one pass:

  • per detector, an OVERALL total plus three orthogonal breakdowns:
      - regime_at_signal  (bull / bear / n-d — old rows predate the column)
      - tone              (bull / bear)
      - strength band     (<60 / 60-74 / >=75 / n-d for null strength)
  • per cell: n, absolute hit-rate, market-neutral hit-rate (over rows where
    `mkt_neutral_hit` is not null — the universe benchmark can be missing),
    and the mean forward return.

HONESTY GUARDRAIL: every cell carries `low_confidence: n < min_n` (default 30,
mirroring `signal_drift_service._DEFAULT_MIN_N` and the harness's per-detector
reporting floor) — the UI must render thin cells as suggestive, not conclusive.
The `meta` envelope states the warehouse's actual coverage (total rows,
detectors present vs the 17-detector universe, date range) because the
warehouse is young: long-horizon (63d) outcomes mature months after their
signals, so entire detectors are still absent. Saying so beats implying
completeness.

Read-only, no caching: the warehouse is small (~1.3k rows today, one row per
matured signal alert ever) and grows by a handful per scan, so a single column
SELECT + in-Python bucketing is microseconds — far below caching territory.
Archived alerts (user-flagged irrelevant) are excluded, matching the drift
monitor's convention.

All rates are PERCENTAGES (0..100) to match the calibration artifact and the
rest of the platform UI; `avg_fwd_return` is likewise a percentage (the stored
`fwd_return` is a ratio).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome
from app.signals.horizon import _PRIOR

# Honesty floor: cells with fewer matured outcomes than this are flagged
# `low_confidence` (mirrors signal_drift_service._DEFAULT_MIN_N = 30).
_DEFAULT_MIN_N = 30

# Fixed bucket orders so the UI renders stable columns. "n/d" (non disponibile)
# collects rows where the dimension is null: legacy alerts without a stored
# strength, and outcome rows whose regime couldn't be computed (no EMA200).
_REGIME_ORDER: tuple[str, ...] = ("bull", "bear", "flat", "n/d")
_TONE_ORDER: tuple[str, ...] = ("bull", "bear")
_STRENGTH_ORDER: tuple[str, ...] = ("<60", "60-74", ">=75", "n/d")


def _strength_band(strength: int | None) -> str:
    """Bucket a Forza value: <60 / 60-74 / >=75, null → 'n/d'."""
    if strength is None:
        return "n/d"
    if strength < 60:
        return "<60"
    if strength < 75:
        return "60-74"
    return ">=75"


def _cell(key: str, rows: Sequence, min_n: int) -> dict:
    """Aggregate one bucket of outcome rows into a display cell.

    `mkt_neutral_hit_rate` is computed ONLY over rows that carry a market-
    neutral label (the universe benchmark can be missing for a trigger date);
    when none do, it is None rather than a misleading 0.
    """
    n = len(rows)
    abs_rate = sum(r.abs_hit for r in rows) / n * 100.0
    mkt_labels = [r.mkt_neutral_hit for r in rows if r.mkt_neutral_hit is not None]
    mkt_rate = (sum(mkt_labels) / len(mkt_labels) * 100.0) if mkt_labels else None
    avg_fwd = sum(r.fwd_return for r in rows) / n * 100.0  # ratio → percent
    return {
        "key": key,
        "n": n,
        "abs_hit_rate": round(abs_rate, 1),
        "mkt_neutral_hit_rate": round(mkt_rate, 1) if mkt_rate is not None else None,
        "avg_fwd_return": round(avg_fwd, 2),
        "low_confidence": n < min_n,
    }


def _breakdown(
    rows: Sequence, key_fn: Callable, order: tuple[str, ...], min_n: int
) -> list[dict]:
    """Bucket `rows` by `key_fn` and emit cells in the fixed `order`, skipping
    empty buckets (the UI renders only what exists)."""
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    return [_cell(k, groups[k], min_n) for k in order if k in groups]


def compute_detector_performance(db: Session, *, min_n: int = _DEFAULT_MIN_N) -> dict:
    """The full detector × regime × tone × strength-band performance cube.

    Returns {"meta": {...}, "detectors": [...]} matching
    `app.schemas.platform.DetectorPerformanceOut`. Detectors are sorted by
    descending total n (the best-evidenced first). Read-only.
    """
    rows = db.execute(
        select(
            SignalOutcome.detector,
            SignalOutcome.regime_at_signal,
            SignalOutcome.tone,
            SignalOutcome.strength,
            SignalOutcome.abs_hit,
            SignalOutcome.mkt_neutral_hit,
            SignalOutcome.fwd_return,
            SignalOutcome.signal_date,
        )
        .join(Alert, Alert.id == SignalOutcome.alert_id)
        .where(Alert.archived_at.is_(None))
    ).all()

    by_detector: dict[str, list] = defaultdict(list)
    for r in rows:
        by_detector[r.detector].append(r)

    detectors: list[dict] = []
    for name, det_rows in sorted(
        by_detector.items(), key=lambda kv: (-len(kv[1]), kv[0])
    ):
        detectors.append({
            "detector": name,
            "total": _cell("totale", det_rows, min_n),
            "by_regime": _breakdown(
                det_rows, lambda r: r.regime_at_signal or "n/d", _REGIME_ORDER, min_n
            ),
            "by_tone": _breakdown(det_rows, lambda r: r.tone, _TONE_ORDER, min_n),
            "by_strength": _breakdown(
                det_rows, lambda r: _strength_band(r.strength), _STRENGTH_ORDER, min_n
            ),
        })

    dates = [r.signal_date for r in rows]
    meta = {
        "total_rows": len(rows),
        "n_detectors": len(by_detector),
        # The full detector universe (17) — so the UI can say "9/17 coperti"
        # instead of implying the table is complete.
        "n_detectors_universe": len(_PRIOR),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "min_n": min_n,
        "computed_at": datetime.now(UTC).isoformat(),
    }
    return {"meta": meta, "detectors": detectors}
