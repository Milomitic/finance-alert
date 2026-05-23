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


def compute_performance(
    db: Session,
    *,
    days: int = 90,
    windows: tuple[int, ...] = (1, 5, 20),
) -> list[RulePerformance]:
    """Walk signal alerts fired in the last `days` days, compute forward
    returns over each window, aggregate per signal_name.

    Returns sorted by total_alerts desc — the signal with the most fires
    appears first so the user sees the heavy-hitters' performance
    immediately.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(Alert)
        .where(
            Alert.triggered_at >= cutoff,
            Alert.archived_at.is_(None),
            Alert.signal_name.is_not(None),
        )
    ).scalars().all()

    if not rows:
        return []

    # Group by "signal:<name>", collect (stock_id, signal_date) pairs.
    by_kind: dict[str, list[tuple[int, date]]] = {}
    stock_ids: set[int] = set()
    for alert in rows:
        if not alert.signal_name:
            continue
        kind = f"signal:{alert.signal_name}"
        # `signal_date` is the bar where the signal matched; falls back
        # to triggered_at's date for legacy rows.
        sig_d = alert.signal_date or alert.triggered_at.date()
        by_kind.setdefault(kind, []).append((alert.stock_id, sig_d))
        stock_ids.add(alert.stock_id)

    if not by_kind:
        return []

    bars_by_stock = _load_bars(db, stock_ids)

    out: list[RulePerformance] = []
    for kind, signals in by_kind.items():
        # kind is "signal:<name>"; extract just the name for tone lookup
        signal_name = kind[len("signal:"):]
        tone = _SIGNAL_TONE.get(signal_name, "neutral")
        per_window: dict[int, WindowStats] = {}
        for w in windows:
            rets: list[float] = []
            hits = 0
            counted = 0
            for stock_id, sig_d in signals:
                fwd = _forward_close(bars_by_stock, stock_id, sig_d, w)
                if fwd is None:
                    continue
                signal_close, forward_close = fwd
                if signal_close <= 0:
                    continue
                ret = (forward_close - signal_close) / signal_close * 100.0
                rets.append(ret)
                # Hit = forward return matched directional expectation
                if tone == "bullish" and ret > 0:
                    hits += 1
                elif tone == "bearish" and ret < 0:
                    hits += 1
                if tone in ("bullish", "bearish"):
                    counted += 1
            mean_pct = statistics.fmean(rets) if rets else None
            median_pct = statistics.median(rets) if rets else None
            hit_rate = (hits / counted) if counted > 0 else None
            per_window[w] = WindowStats(
                count=len(rets),
                mean_pct=mean_pct,
                median_pct=median_pct,
                hit_rate=hit_rate,
            )
        out.append(
            RulePerformance(
                rule_kind=kind,
                tone=tone,
                total_alerts=len(signals),
                stats=per_window,
            )
        )

    out.sort(key=lambda r: r.total_alerts, reverse=True)
    return out
