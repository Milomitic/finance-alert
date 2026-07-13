"""Does multi-horizon agreement predict a BIGGER move (justifying a wider TP2)?

`multi_horizon` (confluence_service) flags a ticker whose prevailing-direction
signals span >=2 distinct horizons on the same day — a long-term trend + a
short-term trigger concurring. A prior note claims a ~+0.8%/30d bull drift edge;
before letting it widen targets we re-validate it AND, crucially, test whether
such setups RUN FURTHER (reach TP2 before the stop more often) — a higher
hit-rate alone would not justify a wider profit target.

Method (no look-ahead, same replay as the other outcome studies): at each obs
bar, run detect_signals(); a match is "multi-horizon" iff its OWN tone side has
>=2 distinct detector horizons among the matches at that bar. Bucket the
forward outcome by (tone, multi_horizon): directional drift excess, TP1-reach
and TP2-reach (path-based, before the structural stop, within the horizon).

Read-only. Bull and bear reported separately (the claimed edge is bull-only).

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.multihorizon_outcomes --sample 60 --step 25
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np
from loguru import logger

from app.scripts.signal_detector_outcomes import (
    _PLAYBOOK_HZ,
    H_SHORT,
    STOP_CAP_ATR,
    _detector_horizon,
    _load_universe,
    _universe_mean_fwd,
)
from app.signals.context import build_context
from app.signals.horizon import classify_horizon
from app.signals.runner import detect_signals

# TP2 geometry mirrors frontend tradePlaybook.ts HZ table: (tp2R, tp2Cap_ATR).
_TP2: dict[str, tuple[float, float]] = {
    "short": (6.0, 3.6), "medium": (3.0, 18.0), "long": (4.5, 14.0),
}


def _reach(s, i: int, m, *, highs: np.ndarray, lows: np.ndarray) -> tuple[float, float] | None:
    """(tp1_hit, tp2_hit) — each 1.0 if reached BEFORE the structural stop within
    the horizon, else 0.0. None when the playbook has no usable level (skip)."""
    entry = float(s.closes[i])
    if not (entry > 0):
        return None
    inv = m.invalidation
    level = inv.get("level") if isinstance(inv, dict) else None
    if not (isinstance(level, (int, float)) and np.isfinite(level) and level > 0):
        return None
    ctx = build_context(s.df.iloc[: i + 1])
    atr = ctx.atr
    if atr is None or not np.isfinite(atr) or atr <= 0:
        atr = entry * 0.02
    hz = classify_horizon(m.name, m.chain)
    P = _PLAYBOOK_HZ.get(hz, _PLAYBOOK_HZ["medium"])
    H = int(P["H"])
    sign = 1 if m.tone == "bull" else -1
    R = min(max(abs(entry - level), P["floor"] * atr), STOP_CAP_ATR * atr)
    if R <= 0:
        return None
    stop = entry - sign * R
    t1 = entry + sign * min(P["tp1R"] * R, P["tp1Cap"] * atr)
    tp2R, tp2Cap = _TP2.get(hz, _TP2["medium"])
    t2 = entry + sign * min(tp2R * R, tp2Cap * atr)
    n = len(s.closes)
    last = min(i + H, n - 1)
    tp1 = tp2 = 0.0
    for k in range(i + 1, last + 1):
        hi, lo = highs[k], lows[k]
        if sign > 0:
            hit_stop, h1, h2 = lo <= stop, hi >= t1, hi >= t2
        else:
            hit_stop, h1, h2 = hi >= stop, lo <= t1, lo <= t2
        if hit_stop:
            return (tp1, tp2)  # same-bar target = stop-first (not yet awarded)
        if h1:
            tp1 = 1.0
        if h2:
            tp2 = 1.0
            return (tp1, tp2)
    return (tp1, tp2)


def run(*, sample: int, step: int, window: int, min_bars: int) -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        logger.info(f"[mh-outcomes] loading universe (sample={sample}) ...")
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
        logger.info(f"[mh-outcomes] {len(universe)} stocks")
        if not universe:
            print("No eligible stocks.")
            return
        umean = _universe_mean_fwd(universe)
        date_to_idx = umean["_date_to_idx"]

        # (tone, mh) -> list of (dir_excess, tp1|None, tp2|None)
        rows: dict[tuple[str, bool], list[tuple[float, float | None, float | None]]] = defaultdict(list)
        n_signals = 0

        for sidx, s in enumerate(universe):
            df = s.df
            c = s.closes
            n = len(c)
            highs = df["high"].to_numpy(dtype="float64")
            lows = df["low"].to_numpy(dtype="float64")
            for i in range(window, n - H_SHORT, step):
                win = df.iloc[i - window:i + 1].reset_index(drop=True)
                try:
                    matches = detect_signals(win)
                except Exception:  # noqa: BLE001
                    continue
                if not matches:
                    continue
                # Horizons present on each side at THIS bar (no look-ahead).
                bull_hz = {classify_horizon(m.name, m.chain) for m in matches if m.tone == "bull"}
                bear_hz = {classify_horizon(m.name, m.chain) for m in matches if m.tone == "bear"}
                di = date_to_idx.get(s.dates[i])
                for m in matches:
                    h = _detector_horizon(m.name)
                    if i + h >= n or c[i] <= 0:
                        continue
                    mh = (m.tone == "bull" and len(bull_hz) >= 2) or \
                         (m.tone == "bear" and len(bear_hz) >= 2)
                    mhf = umean[h]
                    mean = mhf[di] if di is not None else np.nan
                    if not np.isfinite(mean):
                        continue
                    fwd = c[i + h] / c[i] - 1.0
                    dir_excess = (fwd - mean) if m.tone == "bull" else -(fwd - mean)
                    reach = _reach(s, i, m, highs=highs, lows=lows)
                    tp1 = reach[0] if reach else None
                    tp2 = reach[1] if reach else None
                    rows[(m.tone, mh)].append((dir_excess, tp1, tp2))
                    n_signals += 1
            if (sidx + 1) % 25 == 0:
                logger.info(f"[mh-outcomes] {sidx + 1}/{len(universe)} stocks, {n_signals:,} signals")

        logger.info(f"[mh-outcomes] {n_signals:,} signals")
        print(f"\n{'#'*72}\n#  MULTI-HORIZON OUTCOME STUDY  (universe={len(universe)}, signals={n_signals:,})")
        print("#  driftExcess% = market-neutral forward drift (the '+0.8%/30d' claim)")
        print(f"#  tp1%/tp2% = reach TP1 / TP2 before the structural stop within horizon\n{'#'*72}")
        print(f"\n{'tone':>5}{'multiHz':>9}{'n':>8}{'driftEx%':>10}{'tp1%':>8}{'tp2%':>8}{'reachN':>8}")
        for tone in ("bull", "bear"):
            for mh in (False, True):
                arr = rows.get((tone, mh), [])
                if not arr:
                    continue
                drift = float(np.mean([a[0] for a in arr])) * 100
                t1v = [a[1] for a in arr if a[1] is not None]
                t2v = [a[2] for a in arr if a[2] is not None]
                tp1 = (np.mean(t1v) * 100) if t1v else float("nan")
                tp2 = (np.mean(t2v) * 100) if t2v else float("nan")
                print(f"{tone:>5}{str(mh):>9}{len(arr):>8}{drift:>10.3f}{tp1:>8.1f}{tp2:>8.1f}{len(t1v):>8}")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--step", type=int, default=25)
    ap.add_argument("--window", type=int, default=400)
    ap.add_argument("--min-bars", type=int, default=400)
    a = ap.parse_args()
    run(sample=a.sample, step=a.step, window=a.window, min_bars=a.min_bars)
