"""Realised calibration of the signal engine, read from the outcome warehouse.

Bucket matured signal outcomes by Forza band, by nature (continuation vs
reversal) and by stated horizon, and report the market-neutral hit rate each
bucket actually achieved. Consumed by `kpi_service` and the Diagnostics
calibration panel.

WHY THIS NO LONGER REPLAYS `ohlcv_daily` (2026-09-16)
-----------------------------------------------------
Until this date the panel replayed forward closes for alerts that were NOT
ARCHIVED, and read "esiti maturati: 3" while the warehouse held 4,830. It is
the filter that was removed from the warehouse's other three consumers on
2026-09-05: archival tracks AGE, and so does maturation, so the two select
opposite ends of one axis. The old docstring said this path "has not been
re-measured"; measured, it hid 99.9% of the population.

It also disagreed with every other efficacy number in the app on two counts:
it scored the ABSOLUTE hit (a bull signal in a rising market booked the drift
as skill) and it read the retired `confidence` field. The warehouse is the
documented single source of truth for whether a signal worked, so this reads
it: `mkt_neutral_hit`, `strength`, every row regardless of archival.

`compute_performance` and its replay went away on 2026-09-05 for the same
reason; see `detector_performance_service`.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome

#: The horizons the warehouse actually labels. A requested window is snapped to
#: the nearest one: there is no 20-day outcome to read, only a 21-day one.
WAREHOUSE_HORIZONS = (5, 21, 63)

# In-process memo: the Diagnostics hooks hit this repeatedly and the warehouse
# only grows at scan end. Invalidated by a cheap fingerprint (see below).
_MEMO: dict[tuple, tuple[tuple, object]] = {}


def snap_horizon(window: int) -> int:
    """The warehouse horizon closest to `window` (ties go to the shorter)."""
    return min(WAREHOUSE_HORIZONS, key=lambda h: (abs(h - window), h))


def _mutation_token(db: Session) -> tuple:
    """Newest outcome id + row count: maturation appends, a rebuild rewrites,
    and either flips at least one component."""
    return tuple(db.execute(
        select(func.max(SignalOutcome.id), func.count(SignalOutcome.id))
    ).one())


def load_calibration_seed() -> dict | None:
    """Backtest-derived calibration reference (hit-rate + forward return by
    confidence x horizon), shown beside the live numbers as a reference. None
    if the seed file is absent."""
    import pathlib
    fp = pathlib.Path(__file__).resolve().parent.parent / "data" / "calibration_seed.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# --- Calibration: Forza band + nature + horizon hit-rate at one horizon ------
_STRENGTH_BUCKETS = [(60, 70), (70, 80), (80, 90), (90, 101)]


@dataclass(frozen=True)
class CalibrationBucket:
    label: str
    count: int
    hit_rate: float | None
    mean_pct: float | None
    median_pct: float | None


@dataclass(frozen=True)
class Calibration:
    days: int | None
    window: int
    #: Every matured outcome at `window`, in the period. The buckets below can
    #: sum to less: an outcome without a Forza, a nature or a stated horizon
    #: still exists and still counts here.
    total: int
    by_confidence: list[CalibrationBucket]
    by_nature: list[CalibrationBucket]
    by_horizon: list[CalibrationBucket]


def compute_calibration(
    db: Session, *, days: int | None = None, window: int = 21
) -> Calibration:
    """Does higher Forza -> higher realised market-neutral hit rate?

    `days=None` (the default) reads the WHOLE warehouse; a number restricts to
    signals dated within that many days. `window` is snapped to a warehouse
    horizon."""
    horizon = snap_horizon(window)
    key = ("calib", days, horizon)
    token = _mutation_token(db)
    hit = _MEMO.get(key)
    if hit is not None and hit[0] == token:
        return hit[1]  # type: ignore[return-value]
    out = _compute_calibration(db, days, horizon)
    _MEMO[key] = (token, out)
    return out


def _snapshot_horizon(snap: str | None) -> str | None:
    if not snap:
        return None
    try:
        hz = json.loads(snap).get("horizon")
    except (ValueError, TypeError, AttributeError):
        return None
    return hz if hz in ("short", "medium", "long") else None


def _compute_calibration(db: Session, days: int | None, horizon: int) -> Calibration:
    from app.services.alert_service import _CONTINUATION_SIGNALS, _REVERSAL_SIGNALS

    stmt = (
        select(
            SignalOutcome.detector, SignalOutcome.strength,
            SignalOutcome.mkt_neutral_hit, SignalOutcome.fwd_return, Alert.snapshot,
        )
        .join(Alert, Alert.id == SignalOutcome.alert_id, isouter=True)
        .where(SignalOutcome.horizon_days == horizon)
    )
    if days is not None:
        stmt = stmt.where(
            SignalOutcome.signal_date >= (datetime.now(UTC) - timedelta(days=days)).date()
        )
    rows = db.execute(stmt).all()

    conf_acc: dict[str, list[tuple[float, int | None]]] = {}
    nat_acc: dict[str, list[tuple[float, int | None]]] = {}
    hz_acc: dict[str, list[tuple[float, int | None]]] = {}

    for detector, strength, mkt_hit, fwd_return, snapshot in rows:
        # `fwd_return` is stored as a ratio; the panel reads percent.
        item = (float(fwd_return) * 100.0, mkt_hit)
        if strength is not None:
            for lo, hi in _STRENGTH_BUCKETS:
                if lo <= strength < hi:
                    conf_acc.setdefault(f"{lo}-{hi - 1}", []).append(item)
                    break
        nat = (
            "continuazione" if detector in _CONTINUATION_SIGNALS
            else "inversione" if detector in _REVERSAL_SIGNALS else None
        )
        if nat:
            nat_acc.setdefault(nat, []).append(item)
        hz = _snapshot_horizon(snapshot)
        if hz:
            hz_acc.setdefault(hz, []).append(item)

    def mk(label: str, items: list[tuple[float, int | None]]) -> CalibrationBucket:
        rets = [r for r, _ in items]
        # An outcome with no universe benchmark on its day has no market-neutral
        # label: it counts in `count` and stays out of the rate, never as a miss.
        hits = [h for _, h in items if h is not None]
        return CalibrationBucket(
            label=label,
            count=len(items),
            hit_rate=(sum(hits) / len(hits)) if hits else None,
            mean_pct=statistics.fmean(rets) if rets else None,
            median_pct=statistics.median(rets) if rets else None,
        )

    by_conf = [
        mk(f"{lo}-{hi - 1}", conf_acc.get(f"{lo}-{hi - 1}", []))
        for lo, hi in _STRENGTH_BUCKETS
    ]
    by_nat = [mk(n, nat_acc.get(n, [])) for n in ("continuazione", "inversione")]
    by_hz = [mk(h, hz_acc.get(h, [])) for h in ("short", "medium", "long")]
    return Calibration(
        days=days, window=horizon, total=len(rows),
        by_confidence=by_conf, by_nature=by_nat, by_horizon=by_hz,
    )
