"""Detector-LEVEL outcome study (the conjunction, not the marginal factor).

Companion to signal_factor_outcomes.py. That script measured each factor's raw
magnitude in ISOLATION and found most have ~no directional edge market-neutral
(several mean-revert). But a detector fires only on the CONJUNCTION of its
factors + gates + trend context, which may carry edge the marginals don't.

This script answers, by re-running the PRODUCTION detectors over history:
  1. Per detector — realised market-neutral forward hit-rate / edge at its
     natural horizon (the detector's base rate).
  2. Does the CURRENT `confidence` predict the outcome? (hit-rate bucketed by
     confidence) — i.e. is the number we're about to replace actually
     informative, and is detector-level the better basis for Probabilità?

METHOD
══════
  • For a sampled universe and a coarse observation grid, call the real
    detect_signals() on a 500-bar TRAILING window ending at each obs bar
    (enough for EMA200 + 52w-high + chains; caps per-call cost regardless of
    how deep in history the obs is — and stays faithful, since the extractors
    only use a recent window anyway).
  • Forward return = close-to-close from the OBS bar (the detection date — when
    you'd act) over the detector's horizon, market-neutral (minus the universe
    mean that date). Directional: bull→+excess, bear→−excess.
  • No look-ahead: the window ends at the obs bar; the forward return is the
    only thing that looks past it.

Read-only; touches no production tables.

USAGE
═════
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.signal_detector_outcomes
      --sample N      use first N eligible stocks (default 300)
      --step N        bars between observation dates (default 42 ≈ bi-monthly)
      --window N      trailing window bars fed to detect_signals (default 500)
      --min-bars N    require >= N bars of history (default 1000)
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np
from loguru import logger

from app.scripts.signal_factor_outcomes import (
    H_LONG,
    H_MED,
    H_SHORT,
    _load_universe,
    _universe_mean_fwd,
)
from app.signals.horizon import _PRIOR
from app.signals.runner import detect_signals

_H_BY_HORIZON = {"short": H_SHORT, "medium": H_MED, "long": H_LONG}


def _detector_horizon(name: str) -> int:
    return _H_BY_HORIZON.get(_PRIOR.get(name, "medium"), H_MED)


def run(*, sample: int, step: int, window: int, min_bars: int) -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        logger.info(f"[detector-outcomes] loading universe (sample={sample}) ...")
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
        logger.info(f"[detector-outcomes] {len(universe)} stocks")
        if not universe:
            print("No eligible stocks.")
            return
        umean = _universe_mean_fwd(universe)
        date_to_idx = umean["_date_to_idx"]

        # Accumulators.
        per_det: dict[str, list[tuple[float, int]]] = defaultdict(list)  # (dir_excess, conf)
        n_calls = 0
        n_signals = 0

        for sidx, s in enumerate(universe):
            df = s.df
            c = s.closes
            n = len(c)
            for i in range(window, n - H_SHORT, step):
                win = df.iloc[i - window:i + 1].reset_index(drop=True)
                n_calls += 1
                try:
                    matches = detect_signals(win)
                except Exception:  # noqa: BLE001
                    continue
                if not matches:
                    continue
                di = date_to_idx.get(s.dates[i])
                for m in matches:
                    h = _detector_horizon(m.name)
                    if i + h >= n or c[i] <= 0:
                        continue
                    mh = umean[h]
                    mean = mh[di] if di is not None else np.nan
                    if not np.isfinite(mean):
                        continue
                    fwd = c[i + h] / c[i] - 1.0
                    excess = fwd - mean
                    dir_excess = excess if m.tone == "bull" else -excess
                    per_det[m.name].append((dir_excess, int(m.confidence)))
                    n_signals += 1
            if (sidx + 1) % 25 == 0:
                logger.info(f"[detector-outcomes] {sidx + 1}/{len(universe)} stocks, "
                            f"{n_signals:,} signals so far")

        logger.info(f"[detector-outcomes] {n_calls:,} detect calls, {n_signals:,} signals")

        print(f"\n{'#'*78}\n#  DETECTOR-LEVEL OUTCOME STUDY (the conjunction)")
        print(f"#  universe={len(universe)}  detect_calls={n_calls:,}  signals={n_signals:,}")
        print(f"#  market-neutral excess fwd return from the detection bar\n{'#'*78}")
        print(f"\n{'detector':<24}{'n':>8}{'hit%':>8}{'edge%':>9}{'horizon':>9}")
        print("-" * 78)
        rows = []
        for name in sorted(per_det, key=lambda k: -len(per_det[k])):
            arr = per_det[name]
            if len(arr) < 30:
                continue
            de = np.array([a[0] for a in arr])
            hit = float((de > 0).mean()) * 100
            edge = float(de.mean()) * 100
            rows.append((name, len(arr), hit, edge))
            print(f"{name:<24}{len(arr):>8}{hit:>8.1f}{edge:>+9.2f}{_detector_horizon(name):>8}d")

        # Pooled: does CURRENT confidence predict the outcome?
        all_pairs = [p for arr in per_det.values() for p in arr]
        print(f"\n{'='*78}\n  IS CURRENT `confidence` PREDICTIVE?  (pooled, n={len(all_pairs):,})\n{'='*78}")
        print(f"  {'confidence band':<18}{'n':>8}{'hit%':>8}{'edge%':>9}")
        bands = [(0, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
        for lo, hi in bands:
            sub = [de for de, conf in all_pairs if lo <= conf < hi]
            if not sub:
                continue
            a = np.array(sub)
            print(f"  [{lo:>3},{hi:>3})        {len(a):>8}{(a>0).mean()*100:>8.1f}{a.mean()*100:>+9.2f}")
        print("\n  If hit% RISES with the confidence band, the current score is")
        print("  predictive; if FLAT, it's measuring pattern-strength not probability")
        print("  — which is exactly why we split it into Forza + Probabilita.\n")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--step", type=int, default=42)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--min-bars", type=int, default=1000)
    args = ap.parse_args()
    run(sample=args.sample, step=args.step, window=args.window, min_bars=args.min_bars)
