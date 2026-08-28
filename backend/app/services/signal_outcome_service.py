"""Maturation of the signal_outcomes warehouse.

For every signal alert whose forward horizon has fully elapsed in stored
ohlcv_daily, write ONE labeled-outcome row (absolute hit + market-neutral skill
+ causal regime). This is the SINGLE source of truth for forward outcomes,
replacing the duplicated forward-hit logic across signal_drift_service /
signal_detector_outcomes / rule_performance_service.

No-look-ahead is structural: a row is created only once the forward bar exists,
and the regime is computed from data available AT the trigger bar.

Run incrementally at the end of a scan (mature_outcomes), or as a one-off
backfill (app.scripts.backfill_signal_outcomes). Idempotent: alerts that already
have an outcome row are skipped (unique alert_id).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
from loguru import logger
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, SignalOutcome, Stock
from app.services.signal_drift_service import _horizon_days

# EMA span for the causal regime label at the trigger bar.
_REGIME_EMA = 200


def _to_date(v: object) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _snapshot_fields(snapshot: str | None) -> tuple[str | None, int | None, int | None]:
    """(tone, strength, probability) from an Alert.snapshot JSON blob."""
    try:
        s = json.loads(snapshot) if snapshot else {}
    except (ValueError, TypeError):
        return None, None, None
    tone = s.get("tone")
    st = s.get("strength")
    pr = s.get("probability")
    return (
        tone if tone in ("bull", "bear") else None,
        int(st) if isinstance(st, (int, float)) else None,
        int(pr) if isinstance(pr, (int, float)) else None,
    )


def _rows_to_arrays(
    rows: list[tuple[int, object, float]], keep: set[int] | None = None
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    by_stock: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for sid, d, c in rows:
        if keep is not None and sid not in keep:
            continue
        dd = _to_date(d)
        if dd is not None and c is not None:
            by_stock[sid].append((dd, float(c)))
    out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for sid, seq in by_stock.items():
        ds = np.array([x[0] for x in seq], dtype=object)
        cs = np.array([x[1] for x in seq], dtype="float64")
        out[sid] = (ds, cs)
    return out


def _load_universe_closes(
    db: Session, *, since: date | None = None, exclude_etf: bool = False
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Per stock: (dates[], closes[]) ascending. Lightweight column select.

    `since` trims the load to `date >= since` for the market-neutral benchmark:
    the universe forward-mean at a trigger date pairs each bar positionally with
    the one H ahead, and trimming only the *pre-trigger* tail leaves that pairing
    (and every mean at a pending trigger date) numerically identical — while
    turning a full-table scan into a ~90-day slice on the incremental path.

    `exclude_etf` drops instrument_type='etf' stocks from the load: the
    market-neutral benchmark population must be COMPANIES only (a 3x leveraged
    ETF's ±10% days distort the universe forward-mean every signal is measured
    against). Per-stock series for an ETF's OWN alerts stay loadable via
    `_load_stock_closes` — only the benchmark population changes."""
    stmt = select(OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.close)
    if since is not None:
        stmt = stmt.where(OhlcvDaily.date >= since)
    if exclude_etf:
        etf_ids = db.execute(
            select(Stock.id).where(Stock.instrument_type == "etf")
        ).scalars().all()
        if etf_ids:
            stmt = stmt.where(OhlcvDaily.stock_id.not_in(etf_ids))
    rows = db.execute(stmt.order_by(OhlcvDaily.stock_id, OhlcvDaily.date)).all()
    return _rows_to_arrays(rows)


def _load_stock_closes(
    db: Session, stock_ids: set[int]
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Full-history (dates[], closes[]) for ONLY the given stocks. Used for the
    per-alert entry/forward/trigger lookups and the causal regime EMA200 — which
    needs each stock's COMPLETE series to converge, so it cannot be windowed.
    On the incremental scan path `stock_ids` is just the handful of stocks whose
    alerts matured this cycle; on the one-off backfill it is the whole universe."""
    if not stock_ids:
        return {}
    stmt = select(OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.close)
    # SQLite caps bound params at 999. Past that (backfill: pending == universe)
    # skip the IN clause and load all rows, then keep only the wanted stocks.
    load_all = len(stock_ids) > 900
    if not load_all:
        stmt = stmt.where(OhlcvDaily.stock_id.in_(stock_ids))
    rows = db.execute(stmt.order_by(OhlcvDaily.stock_id, OhlcvDaily.date)).all()
    return _rows_to_arrays(rows, keep=stock_ids if load_all else None)


# A date needs at least this many stocks before its benchmark means anything.
# Same floor as the conditional-screen replay: a median over three names is
# not a market.
_MIN_UNIVERSE_PER_DATE = 10


def _universe_fwd_medians(
    closes_by_stock: dict[int, tuple[np.ndarray, np.ndarray]], horizon: int
) -> dict[date, float]:
    """{trigger_date: MEDIAN H-day-forward return across the universe}.

    THE MEDIAN, NOT THE MEAN, and the distinction is the whole point of this
    function. Cross-sectional forward returns are right-skewed, so under zero
    skill P(beat the mean) is BELOW 50% — measured on this universe: 47.4% at
    H=5, 45.3% at H=21, 42.2% at H=63. A bull signal therefore starts from ~45
    and a bear signal from ~55 before any skill exists, so the zero point of
    `mkt_neutral_hit` moves with tone and horizon and the bias is larger than
    the effect being measured (the whole engine spans 45.7-52.0).

    This is invariant #3 in CLAUDE.md — the lesson of the trend_pullback
    artifact, which a whole conditional-screen grid had to be discarded over.
    `conditional_screen_replay._universe_fwd_medians` honoured it; this path,
    which is what actually reaches the user through `calibration_map.skill`
    and the honesty tags, used the mean. The invariant's regression test lived
    only in `test_conditional_screen.py`, i.e. only on the path that already
    obeyed it.

    Collected per date rather than accumulated: a median needs the whole
    distribution, so the fancy-add trick the mean used does not apply.
    """
    by_date: dict[date, list[float]] = defaultdict(list)
    for ds, cs in closes_by_stock.values():
        if len(cs) <= horizon:
            continue
        c0 = cs[:-horizon]
        cH = cs[horizon:]
        ok = c0 > 0
        rets = cH[ok] / c0[ok] - 1.0
        for d, r in zip(np.asarray(ds, dtype=object)[:-horizon][ok], rets, strict=False):
            by_date[d].append(float(r))
    return {
        d: float(np.median(v))
        for d, v in by_date.items()
        if len(v) >= _MIN_UNIVERSE_PER_DATE
    }


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    """Causal EWM (pandas-equivalent) over a 1-D array."""
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values)
    acc = values[0]
    out[0] = acc
    for i in range(1, len(values)):
        acc = alpha * values[i] + (1 - alpha) * acc
        out[i] = acc
    return out


def _trigger_index(dates: np.ndarray, signal_date: date) -> int | None:
    """First bar index at/after signal_date (None if signal_date is past EOD)."""
    for i, d in enumerate(dates):
        if d >= signal_date:
            return i
    return None


def mature_outcomes(db: Session, *, commit: bool = True) -> int:
    """Write outcome rows for newly-matured signal alerts. Returns rows added."""
    # Anti-join in SQL: only alerts WITHOUT an outcome row come back. The old
    # shape loaded every signal alert + every outcome alert_id into Python and
    # set-differenced them — O(all history) per scan. NOT EXISTS resolves as a
    # point probe per alert on the unique ix_signal_outcomes_alert index, and
    # already-matured alerts never leave the database.
    pending = list(db.execute(
        select(Alert).where(
            Alert.signal_name.is_not(None),
            Alert.signal_date.is_not(None),
            ~exists(select(SignalOutcome.id).where(SignalOutcome.alert_id == Alert.id)),
        )
    ).scalars())
    if not pending:
        return 0

    # Per-alert exact series (entry/forward/trigger + regime EMA200) for ONLY
    # the pending stocks — a handful on the incremental scan path. Full history
    # because the EMA needs a long warmup to converge to the same value the
    # backfill path produces.
    pending_sids = {a.stock_id for a in pending}
    closes = _load_stock_closes(db, pending_sids)

    # Universe market-neutral benchmark: companies only (ETFs excluded — see
    # _load_universe_closes), and only the date window the pending triggers
    # reach (exact — see _load_universe_closes). This is the load that used
    # to scan the entire 2.4M-row table at every scan end.
    min_td = min(a.signal_date for a in pending)
    uni_closes = _load_universe_closes(
        db, since=min_td - timedelta(days=10), exclude_etf=True
    )
    horizons = {_horizon_days(a.signal_name) for a in pending}
    medians_by_h: dict[int, dict[date, float]] = {
        h: _universe_fwd_medians(uni_closes, h) for h in horizons
    }
    ema_cache: dict[int, np.ndarray] = {}

    added = 0
    for a in pending:
        sd = a.signal_date
        sb = closes.get(a.stock_id)
        if sb is None:
            continue
        dates, cs = sb
        ti = _trigger_index(dates, sd)
        if ti is None:
            continue
        H = _horizon_days(a.signal_name)
        fi = ti + H
        if fi >= len(cs):
            continue  # horizon not yet elapsed → not matured
        entry = float(cs[ti])
        if entry <= 0:
            continue
        fwd_close = float(cs[fi])
        fwd_ret = fwd_close / entry - 1.0
        tone, strength, probability = _snapshot_fields(a.snapshot)
        if tone is None:
            continue
        abs_hit = 1 if ((tone == "bull" and fwd_ret > 0) or (tone == "bear" and fwd_ret < 0)) else 0

        uni_median = medians_by_h.get(H, {}).get(dates[ti])
        mkt_excess = mkt_hit = None
        if uni_median is not None:
            excess = fwd_ret - uni_median
            mkt_excess = excess if tone == "bull" else -excess
            mkt_hit = 1 if mkt_excess > 0 else 0

        # Causal regime: close vs EMA200 at the trigger bar.
        regime = None
        if a.stock_id not in ema_cache:
            ema_cache[a.stock_id] = _ema(cs, _REGIME_EMA) if len(cs) else np.array([])
        ema_arr = ema_cache[a.stock_id]
        if ti < len(ema_arr) and ema_arr[ti] > 0:
            regime = "bull" if cs[ti] > ema_arr[ti] else "bear"

        db.add(SignalOutcome(
            alert_id=a.id, stock_id=a.stock_id, detector=a.signal_name,
            signal_date=sd, tone=tone, horizon_days=H,
            entry_close=entry, forward_close=fwd_close, fwd_return=fwd_ret,
            universe_mean_fwd=uni_median, mkt_neutral_excess=mkt_excess,
            abs_hit=abs_hit, mkt_neutral_hit=mkt_hit, regime_at_signal=regime,
            strength=strength, probability=probability,
        ))
        added += 1

    if commit and added:
        db.commit()
    logger.info(f"[signal-outcomes] matured {added} new alerts ({len(pending)} pending)")
    return added
