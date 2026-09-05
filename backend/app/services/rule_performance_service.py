"""Realised calibration of the signal engine, replayed from `ohlcv_daily`.

Bucket matured alerts by stated confidence, by nature (continuation vs
reversal) and by horizon, and report the hit rate each bucket actually
achieved. Consumed by `kpi_service` and the Settings calibration panel.

WHAT USED TO BE HERE, AND WHY IT IS NOT (2026-09-05)
----------------------------------------------------
This module also carried `compute_performance` — per-signal forward-return
stats over 1/5/20-day windows, feeding a "signal effectiveness" table in
Settings. That table now reads the `signal_outcomes` warehouse instead (see
`detector_performance_service`), which is the documented single source of
truth for whether a signal worked.

Leaving the replay behind would have left TWO answers to one question, and
they disagreed by construction: this one reported the ABSOLUTE hit rate, so a
bull signal in a rising market scored the market's drift as its own skill. On
the live warehouse `sr_flip` bull read 57.9% absolute against 51.5%
market-neutral. It also treated each alert as an independent observation,
which overlapping forward windows make false.

`_SIGNAL_TONE` went with it — a hand-maintained mirror of the frontend's tone
map, carrying a comment instructing future readers to update it when adding a
signal. Nothing had read it for some time.

Caveats that still apply
------------------------
- No survivorship-bias correction (delisted tickers don't contribute) and no
  transaction costs.
- Forward windows use trading-day-adjacent bars, not calendar days, so
  weekends and holidays don't penalise the metric.
- Archived alerts are excluded. ⚠️ This is the same filter that was removed
  from the outcome warehouse's three consumers on 2026-09-05 after it was
  measured to hide 4,861 of 4,880 matured outcomes there — archival tracks
  AGE, not signal quality, and so does maturation. This path was left alone
  deliberately in that pass; it has not been re-measured here.
"""
from __future__ import annotations

import bisect
import json
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily


@dataclass(frozen=True)
class _StockBars:
    """Parallel date/close arrays for one stock, ascending by date. Kept as
    plain lists (not ORM entities) so the forward-return math touches only the
    two columns it needs and can bisect the date axis."""
    dates: list[date]
    closes: list[float]


def _forward_close(
    bars_by_stock: dict[int, _StockBars],
    stock_id: int,
    signal_date: date,
    window_days: int,
) -> tuple[float, float] | None:
    """Return (signal_close, forward_close) for `stock_id` where
    forward_close is the N-th trading-day bar at or after `signal_date +
    window_days`. None if the bars list is too short.
    """
    bars = bars_by_stock.get(stock_id)
    if not bars:
        return None
    # Bars are pre-sorted ascending by date in `_load_bars`. bisect_left finds
    # the first bar at or after signal_date in O(log n) — the same index the old
    # linear scan produced, without the per-alert full-list walk.
    signal_idx = bisect.bisect_left(bars.dates, signal_date)
    forward_idx = signal_idx + window_days
    if forward_idx >= len(bars.dates):
        return None
    return bars.closes[signal_idx], bars.closes[forward_idx]


def _load_bars(db: Session, *, since: date | None = None) -> dict[int, _StockBars]:
    """Column-projected OHLCV load for the forward-return math, windowed to
    `date >= since`. Loading only (stock_id, date, close) from the date window
    the alerts actually reach — instead of every ORM column of the full 10y
    history for ~900 stocks — cuts this from ~2.25M rows/26s to sub-second.

    No stock-id filter: windowing already bounds the row count (~universe ×
    window trading days), and dropping the `IN (...)` clause sidesteps SQLite's
    999-bound-parameter limit. Stocks without alerts are simply never queried."""
    stmt = select(OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.close)
    if since is not None:
        stmt = stmt.where(OhlcvDaily.date >= since)
    stmt = stmt.order_by(OhlcvDaily.stock_id, OhlcvDaily.date)
    dates: dict[int, list[date]] = {}
    closes: dict[int, list[float]] = {}
    for sid, d, c in db.execute(stmt).all():
        dates.setdefault(sid, []).append(d)
        closes.setdefault(sid, []).append(float(c))
    return {sid: _StockBars(dates[sid], closes[sid]) for sid in dates}


# In-process memo: compute_performance/compute_calibration are hit repeatedly by
# the Settings-page hooks, and the underlying data only changes at scan time.
# Keyed by call args; invalidated by a cheap mutation fingerprint (see below).
_MEMO: dict[tuple, tuple[tuple, object]] = {}


def _mutation_token(db: Session, cutoff: datetime) -> tuple:
    """Cheap fingerprint of everything that can change the stats: the newest
    alert id, the count of live (non-archived) in-window signal alerts, and the
    newest bar date. A scan (new alerts + new bars), a fresh alert, or a user
    archival each flips at least one component → the memo misses and recomputes."""
    max_alert = db.execute(select(func.max(Alert.id))).scalar()
    live_count = db.execute(
        select(func.count(Alert.id)).where(
            Alert.triggered_at >= cutoff,
            Alert.archived_at.is_(None),
            Alert.signal_name.is_not(None),
        )
    ).scalar()
    max_bar = db.execute(select(func.max(OhlcvDaily.date))).scalar()
    return (max_alert, live_count, max_bar)


def _snapshot_tone_conf(snap: str | None) -> tuple[str | None, float | None, str | None]:
    """Parse (tone, confidence, horizon) from an alert snapshot. The snapshot
    carries the signal's own bull/bear tone -- the reliable source -- instead of
    the stale name->tone map (kept above only for backward reference)."""
    if not snap:
        return None, None, None
    try:
        d = json.loads(snap)
    except (ValueError, TypeError):
        return None, None, None
    tone = d.get("tone")
    conf = d.get("confidence")
    hz = d.get("horizon")
    return (tone if tone in ("bull", "bear") else None,
            float(conf) if isinstance(conf, (int, float)) else None,
            hz if hz in ("short", "medium", "long") else None)


def load_calibration_seed() -> dict | None:
    """Backtest-derived calibration reference (hit-rate + forward return by
    confidence x horizon), used to populate the panel immediately while the
    live, maturing calibration accumulates. None if the seed file is absent."""
    import pathlib
    fp = pathlib.Path(__file__).resolve().parent.parent / "data" / "calibration_seed.json"
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _directional_hit(tone: str | None, ret: float) -> bool | None:
    """Did the forward return match the signal direction? None for unknown tone."""
    if tone == "bull":
        return ret > 0
    if tone == "bear":
        return ret < 0
    return None


# --- Calibration: confidence-bucket + nature hit-rate at one horizon --------
_CONF_BUCKETS = [(60, 70), (70, 80), (80, 90), (90, 101)]


@dataclass(frozen=True)
class CalibrationBucket:
    label: str
    count: int
    hit_rate: float | None
    mean_pct: float | None
    median_pct: float | None


@dataclass(frozen=True)
class Calibration:
    days: int
    window: int
    by_confidence: list[CalibrationBucket]
    by_nature: list[CalibrationBucket]
    by_horizon: list[CalibrationBucket]


def compute_calibration(db: Session, *, days: int = 365, window: int = 20) -> Calibration:
    """Does higher confidence -> higher realized hit-rate? Buckets emitted
    alerts by confidence and by nature, computing directional hit-rate + mean/
    median forward return at one horizon. Survivorship-aware: tracks our own
    emitted alerts forward (delisted tickers simply lack forward bars).
    Memoized on the same mutation fingerprint as compute_performance."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    key = ("calib", days, window)
    token = _mutation_token(db, cutoff)
    hit = _MEMO.get(key)
    if hit is not None and hit[0] == token:
        return hit[1]  # type: ignore[return-value]
    out = _compute_calibration(db, cutoff, days, window)
    _MEMO[key] = (token, out)
    return out


def _compute_calibration(
    db: Session, cutoff: datetime, days: int, window: int
) -> Calibration:
    from app.services.alert_service import _CONTINUATION_SIGNALS, _REVERSAL_SIGNALS

    rows = db.execute(
        select(Alert).where(
            Alert.triggered_at >= cutoff,
            Alert.archived_at.is_(None),
            Alert.signal_name.is_not(None),
        )
    ).scalars().all()
    min_signal_date = min(
        (a.signal_date or a.triggered_at.date() for a in rows), default=None
    )
    bars_by_stock = _load_bars(db, since=min_signal_date)

    conf_acc: dict[str, list[tuple[float, bool | None]]] = {}
    nat_acc: dict[str, list[tuple[float, bool | None]]] = {}
    hz_acc: dict[str, list[tuple[float, bool | None]]] = {}

    def conf_label(c: float) -> str | None:
        for lo, hi in _CONF_BUCKETS:
            if lo <= c < hi:
                return f"{lo}-{hi - 1}"
        return None

    for a in rows:
        if not a.signal_name:
            continue
        tone, conf, hz = _snapshot_tone_conf(a.snapshot)
        sig_d = a.signal_date or a.triggered_at.date()
        fwd = _forward_close(bars_by_stock, a.stock_id, sig_d, window)
        if fwd is None:
            continue
        sc, fc = fwd
        if sc <= 0:
            continue
        ret = (fc - sc) / sc * 100.0
        hit = _directional_hit(tone, ret)
        if conf is not None:
            cl = conf_label(conf)
            if cl:
                conf_acc.setdefault(cl, []).append((ret, hit))
        nat = (
            "continuazione" if a.signal_name in _CONTINUATION_SIGNALS
            else "inversione" if a.signal_name in _REVERSAL_SIGNALS else None
        )
        if nat:
            nat_acc.setdefault(nat, []).append((ret, hit))
        if hz:
            hz_acc.setdefault(hz, []).append((ret, hit))

    def mk(label: str, items: list[tuple[float, bool | None]]) -> CalibrationBucket:
        rets = [r for r, _ in items]
        hits = [h for _, h in items if h is not None]
        return CalibrationBucket(
            label=label,
            count=len(items),
            hit_rate=(sum(hits) / len(hits)) if hits else None,
            mean_pct=statistics.fmean(rets) if rets else None,
            median_pct=statistics.median(rets) if rets else None,
        )

    by_conf = [mk(f"{lo}-{hi - 1}", conf_acc.get(f"{lo}-{hi - 1}", [])) for lo, hi in _CONF_BUCKETS]
    by_nat = [mk(n, nat_acc.get(n, [])) for n in ("continuazione", "inversione")]
    by_hz = [mk(h, hz_acc.get(h, [])) for h in ("short", "medium", "long")]
    return Calibration(days=days, window=window, by_confidence=by_conf,
                       by_nature=by_nat, by_horizon=by_hz)
