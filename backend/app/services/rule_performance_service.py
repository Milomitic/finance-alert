"""Signal hit-rate / forward-return statistics.

For every signal alert that fired, look up the underlying stock's price K
days after the signal date and compute the forward return. Aggregate
per signal_name to surface "volume_breakout alerts have a +1.8% median
return after 5 days; rsi_oversold averages -0.4%".

Why this matters
----------------
A signal that fires often but produces zero alpha is noise; one with a
small but consistent edge is real signal. The hit-rate panel turns
historical alert data into a feedback loop the user can use to
evaluate the signal engine's output.

Forward windows: 1d, 5d, 20d (1 day / 1 week / 1 month). Each is a
column in the output. We use trading-day-adjacent OHLCV bars (not
calendar days) so weekends/holidays don't penalize the metric.

Stat shape per (signal, window):
  - count          alerts with enough forward data to compute return
  - mean_pct       arithmetic mean forward return
  - median_pct     more robust to outliers
  - hit_rate       % of alerts where forward return matched the
                   signal's directional expectation:
                     bullish signals → positive forward return
                     bearish signals → negative forward return
                     neutral signals → not computed (None)

Caveats
-------
- We don't account for survivorship bias (delisted tickers don't
  contribute) or transaction costs.
- "Tone" comes from `lib/alertMeta.getAlertKindMeta` on the
  frontend; here we mirror that mapping in `_SIGNAL_TONE` for
  consistency. If the frontend tone changes, update the dict.
- Excludes archived alerts (user-flagged as "no longer relevant").
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily

# Mirror of frontend `getAlertKindMeta` tone classification. Used
# only for the directional hit_rate calculation. Keys are raw signal
# names (without the "signal:" prefix). Update when adding signals
# or shifting an existing signal's directional bias.
_SIGNAL_TONE: dict[str, str] = {
    "rsi_oversold": "bullish",
    "rsi_overbought": "bearish",
    "golden_cross": "bullish",
    "death_cross": "bearish",
    "macd_bullish_cross": "bullish",
    "macd_bearish_cross": "bearish",
    "bollinger_squeeze": "neutral",   # squeeze = expansion expected, no direction
    "bollinger_breakout_up": "bullish",
    "bollinger_breakout_down": "bearish",
    "volume_spike": "neutral",        # direction depends on price action
    "volume_breakout": "bullish",
    "breakout_up": "bullish",
    "breakout_down": "bearish",
    "gap_up": "bullish",
    "gap_down": "bearish",
    "adx_trend_up": "bullish",
    "adx_trend_down": "bearish",
    "mean_reversion_long": "bullish",
    "mean_reversion_short": "bearish",
}


@dataclass(frozen=True)
class WindowStats:
    """Stats for one (rule, window) pair."""
    count: int
    mean_pct: float | None
    median_pct: float | None
    hit_rate: float | None  # 0..1, None for neutral rules


@dataclass(frozen=True)
class RulePerformance:
    rule_kind: str
    tone: str               # "bullish" | "bearish" | "neutral"
    total_alerts: int       # alerts of this kind in window (any forward data)
    stats: dict[int, WindowStats]  # window_days → stats


def _forward_close(
    bars_by_stock: dict[int, list[OhlcvDaily]],
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
    # Bars are pre-sorted ascending by date in `_load_bars`.
    # Find the first bar at or after signal_date.
    signal_idx = None
    for i, b in enumerate(bars):
        if b.date >= signal_date:
            signal_idx = i
            break
    if signal_idx is None:
        return None
    forward_idx = signal_idx + window_days
    if forward_idx >= len(bars):
        return None
    return float(bars[signal_idx].close), float(bars[forward_idx].close)


def _load_bars(
    db: Session, stock_ids: set[int]
) -> dict[int, list[OhlcvDaily]]:
    """Bulk-load OHLCV bars for the requested stocks, ordered ascending
    by date. Returns dict stock_id → list of bars (oldest first)."""
    if not stock_ids:
        return {}
    rows = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id.in_(stock_ids))
            .order_by(OhlcvDaily.stock_id, OhlcvDaily.date)
        )
        .scalars()
        .all()
    )
    out: dict[int, list[OhlcvDaily]] = {}
    for r in rows:
        out.setdefault(r.stock_id, []).append(r)
    return out


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


def compute_performance(
    db: Session,
    *,
    days: int = 90,
    windows: tuple[int, ...] = (1, 5, 20),
) -> list[RulePerformance]:
    """Forward-return stats per signal_name over `days`. Directional hit-rate
    uses each alert's OWN snapshot tone (bull/bear), not a static name map."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(Alert).where(
            Alert.triggered_at >= cutoff,
            Alert.archived_at.is_(None),
            Alert.signal_name.is_not(None),
        )
    ).scalars().all()
    if not rows:
        return []

    by_kind: dict[str, list[tuple[int, date, str | None]]] = {}
    stock_ids: set[int] = set()
    for alert in rows:
        if not alert.signal_name:
            continue
        kind = f"signal:{alert.signal_name}"
        sig_d = alert.signal_date or alert.triggered_at.date()
        tone, _, _ = _snapshot_tone_conf(alert.snapshot)
        by_kind.setdefault(kind, []).append((alert.stock_id, sig_d, tone))
        stock_ids.add(alert.stock_id)
    if not by_kind:
        return []

    bars_by_stock = _load_bars(db, stock_ids)
    out: list[RulePerformance] = []
    for kind, signals in by_kind.items():
        tones = [t for *_, t in signals if t]
        row_tone = max(set(tones), key=tones.count) if tones else "neutral"
        per_window: dict[int, WindowStats] = {}
        for w in windows:
            rets: list[float] = []
            hits = 0
            counted = 0
            for stock_id, sig_d, tone in signals:
                fwd = _forward_close(bars_by_stock, stock_id, sig_d, w)
                if fwd is None:
                    continue
                sc, fc = fwd
                if sc <= 0:
                    continue
                ret = (fc - sc) / sc * 100.0
                rets.append(ret)
                hit = _directional_hit(tone, ret)
                if hit is not None:
                    counted += 1
                    if hit:
                        hits += 1
            per_window[w] = WindowStats(
                count=len(rets),
                mean_pct=statistics.fmean(rets) if rets else None,
                median_pct=statistics.median(rets) if rets else None,
                hit_rate=(hits / counted) if counted > 0 else None,
            )
        out.append(RulePerformance(rule_kind=kind, tone=row_tone,
                                   total_alerts=len(signals), stats=per_window))
    out.sort(key=lambda r: r.total_alerts, reverse=True)
    return out


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
    by_confidence: list["CalibrationBucket"]
    by_nature: list["CalibrationBucket"]
    by_horizon: list["CalibrationBucket"]


def compute_calibration(db: Session, *, days: int = 365, window: int = 20) -> Calibration:
    """Does higher confidence -> higher realized hit-rate? Buckets emitted
    alerts by confidence and by nature, computing directional hit-rate + mean/
    median forward return at one horizon. Survivorship-aware: tracks our own
    emitted alerts forward (delisted tickers simply lack forward bars)."""
    from app.services.alert_service import _CONTINUATION_SIGNALS, _REVERSAL_SIGNALS

    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(Alert).where(
            Alert.triggered_at >= cutoff,
            Alert.archived_at.is_(None),
            Alert.signal_name.is_not(None),
        )
    ).scalars().all()
    bars_by_stock = _load_bars(db, {a.stock_id for a in rows})

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
