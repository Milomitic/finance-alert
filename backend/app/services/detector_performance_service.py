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

REPLAY SEGMENT (B4-5): the four most-fired 63d detectors have ZERO live
warehouse rows (first maturations ~mid-August 2026). The historical-replay
backfill (`app.scripts.backfill_replay_outcomes`) fills that gap — but since
`signal_outcomes.alert_id` is a non-nullable FK, its output lives in an
artifact (`app/data/replay_outcomes_summary.json`) instead of table rows.
This service merges it as a SEPARATE `replay` block in the response: same
cell shape as the live cube, `low_confidence` stamped at read time against
the caller's min_n, and NEVER mixed into the live hit rates (the replay has
no emission-gate survivorship of the live path). Missing artifact → the
block is None and `meta.replay_available` is False.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome
from app.signals.horizon import _PRIOR

# Replay artifact written by `app.scripts.backfill_replay_outcomes`.
# Module-level so tests can monkeypatch it to a tmp path.
_REPLAY_ARTIFACT = Path(__file__).resolve().parent.parent / "data" / "replay_outcomes_summary.json"

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


def _load_replay_summary() -> dict | None:
    """Read the replay artifact (None on absent/corrupt/empty — the segment
    simply doesn't render, mirroring calibration_map's degrade-gracefully
    convention). Read per call, not cached: the file is a few KB and the
    endpoint is on-demand — consistent with this module's no-caching stance."""
    try:
        if not _REPLAY_ARTIFACT.exists():
            return None
        data = json.loads(_REPLAY_ARTIFACT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("detectors"), dict):
        return None
    return data if data["detectors"] else None


def _replay_cell(cell: dict, min_n: int) -> dict:
    """Stamp `low_confidence` on an artifact cell at read time (the artifact
    stores only the counts/rates — the honesty floor is the caller's)."""
    return {**cell, "low_confidence": int(cell.get("n", 0)) < min_n}


def _replay_block(summary: dict, min_n: int) -> dict:
    """Shape the artifact into the response's `replay` segment. Detectors
    sorted by descending total n like the live list."""
    detectors: list[dict] = []
    for name, block in sorted(
        summary["detectors"].items(),
        key=lambda kv: (-int(kv[1].get("total", {}).get("n", 0)), kv[0]),
    ):
        detectors.append({
            "detector": name,
            "total": _replay_cell(block.get("total", {"key": "totale", "n": 0}), min_n),
            "by_regime": [_replay_cell(c, min_n) for c in block.get("by_regime", [])],
            "by_tone": [_replay_cell(c, min_n) for c in block.get("by_tone", [])],
            "by_strength": [_replay_cell(c, min_n) for c in block.get("by_strength", [])],
        })
    return {
        "generated_at": summary.get("generated_at"),
        "n_signals": int(summary.get("n_signals", 0)),
        "date_min": summary.get("date_min"),
        "date_max": summary.get("date_max"),
        "params": summary.get("params"),
        "detectors": detectors,
    }


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

    # Replay segment (B4-5): additive, clearly labeled, never blended into
    # the live cells above.
    replay_summary = _load_replay_summary()

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
        "replay_available": replay_summary is not None,
    }
    return {
        "meta": meta,
        "detectors": detectors,
        "replay": _replay_block(replay_summary, min_n) if replay_summary else None,
    }


def compute_equity_curve(
    db: Session,
    *,
    horizon_days: int = 21,
    detector: str | None = None,
    tone: str | None = None,
    regime: str | None = None,
    strength_min: int | None = None,
) -> dict:
    """Hypothetical cumulative equity from following every matured signal that
    matches the filters, ordered by signal date.

    Two curves: absolute (compound the realised forward returns) and
    market-neutral (compound the tone-signed excess vs the universe mean). This
    is a growth-of-1 ILLUSTRATION — one unit per signal, sequential, with NO
    overlap handling, position sizing, or costs — not a tradeable backtest P&L.
    The market-neutral curve is the honest, beta-stripped read. Read-only over
    the signal_outcomes warehouse.
    """
    stmt = (
        select(
            SignalOutcome.signal_date,
            SignalOutcome.fwd_return,
            SignalOutcome.mkt_neutral_excess,
            SignalOutcome.abs_hit,
        )
        .join(Alert, Alert.id == SignalOutcome.alert_id)
        .where(Alert.archived_at.is_(None))
        .where(SignalOutcome.horizon_days == horizon_days)
        .order_by(SignalOutcome.signal_date.asc(), SignalOutcome.id.asc())
    )
    if detector:
        stmt = stmt.where(SignalOutcome.detector == detector)
    if tone in ("bull", "bear"):
        stmt = stmt.where(SignalOutcome.tone == tone)
    if regime in ("bull", "bear", "flat"):
        stmt = stmt.where(SignalOutcome.regime_at_signal == regime)
    if strength_min is not None:
        stmt = stmt.where(SignalOutcome.strength >= strength_min)

    rows = db.execute(stmt).all()

    eq = 1.0
    eqmn = 1.0
    peak = 1.0
    max_dd = 0.0
    wins = 0
    ret_sum = 0.0
    by_date: dict[str, dict] = {}
    for r in rows:
        eq *= 1.0 + r.fwd_return
        excess = r.mkt_neutral_excess if r.mkt_neutral_excess is not None else 0.0
        eqmn *= 1.0 + excess
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
        wins += int(r.abs_hit or 0)
        ret_sum += r.fwd_return
        # One point per date — the equity after that date's last signal — for a
        # clean, monotone time axis (several signals can share a date).
        by_date[r.signal_date.isoformat()] = {
            "equity": round(eq, 4),
            "equity_mkt_neutral": round(eqmn, 4),
        }

    n = len(rows)
    # Full detector list (unfiltered) so the UI dropdown always offers every one.
    det_names = [
        d
        for (d,) in db.execute(
            select(SignalOutcome.detector).distinct().order_by(SignalOutcome.detector)
        ).all()
    ]
    return {
        "points": [{"date": d, **v} for d, v in by_date.items()],
        "n_signals": n,
        "total_return_pct": round((eq - 1.0) * 100.0, 2),
        "mkt_neutral_return_pct": round((eqmn - 1.0) * 100.0, 2),
        "win_rate_pct": round(wins / n * 100.0, 1) if n else 0.0,
        "avg_return_pct": round(ret_sum / n * 100.0, 2) if n else 0.0,
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "horizon_days": horizon_days,
        "detectors": det_names,
    }
