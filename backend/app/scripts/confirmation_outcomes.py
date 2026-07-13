"""Does co-temporal confirmation stacking predict the forward outcome?

The Phase-1/2 chain enrichment stamps a bounded ``confirmation_count`` (0, 1/3,
2/3, 1) on every technical signal. This study answers the empirical question
that gates Phase 3: do signals with MORE co-temporal confirmations resolve
their way MORE often? It replays detect_signals() over a trailing window (the
same no-look-ahead machinery as signal_detector_outcomes) and buckets the
realised forward hit-rate by confirmation_count — overall and per detector.

If higher buckets show a higher hit-rate, that justifies a calibrated
``confirmation_count`` adjustment in signal_calibration.json (bounded ±8). If
not, the honest result is "no adjustment" — confirmation is display-only.

Read-only (no DB writes); safe to run with uvicorn up, but CPU-heavy.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.confirmation_outcomes --sample 200
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np
from loguru import logger

from app.scripts.signal_detector_outcomes import (
    H_SHORT,
    _detector_horizon,
    _load_universe,
    _trade_playbook_hit,
    _universe_mean_fwd,
)
from app.signals.runner import detect_signals


def _bucket(cc: float) -> int:
    """confirmation_count (0, 1/3, 2/3, 1) -> integer #confirmations 0..3."""
    return int(round((cc or 0.0) * 3))


def run(*, sample: int, step: int, window: int, min_bars: int) -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        logger.info(f"[confirm-outcomes] loading universe (sample={sample}) ...")
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
        logger.info(f"[confirm-outcomes] {len(universe)} stocks")
        if not universe:
            print("No eligible stocks.")
            return
        umean = _universe_mean_fwd(universe)
        date_to_idx = umean["_date_to_idx"]

        # rows: (bucket, abs_hit, tbs_or_None); also per-detector.
        overall: list[tuple[int, float, float | None]] = []
        per_det: dict[str, list[tuple[int, float, float | None]]] = defaultdict(list)
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
                di = date_to_idx.get(s.dates[i])
                for m in matches:
                    if "confirmation_count" not in m.factors:
                        continue  # non-enrichable (fundamental) detector
                    h = _detector_horizon(m.name)
                    if i + h >= n or c[i] <= 0:
                        continue
                    fwd = c[i + h] / c[i] - 1.0
                    abs_hit = 1.0 if ((m.tone == "bull" and fwd > 0)
                                      or (m.tone == "bear" and fwd < 0)) else 0.0
                    tbs = _trade_playbook_hit(s, i, m, highs=highs, lows=lows)
                    b = _bucket(m.factors.get("confirmation_count"))
                    overall.append((b, abs_hit, tbs))
                    per_det[m.name].append((b, abs_hit, tbs))
                    n_signals += 1
            if (sidx + 1) % 25 == 0:
                logger.info(f"[confirm-outcomes] {sidx + 1}/{len(universe)} stocks, "
                            f"{n_signals:,} signals so far")

        logger.info(f"[confirm-outcomes] {n_signals:,} enrichable signals")

        def _report(title: str, rows: list[tuple[int, float, float | None]]) -> None:
            print(f"\n{title}  (n={len(rows):,})")
            print(f"  {'#conf':>5}{'n':>8}{'absHit%':>9}{'tbs%':>8}{'tbsN':>7}")
            for b in (0, 1, 2, 3):
                sub = [r for r in rows if r[0] == b]
                if not sub:
                    continue
                ah = np.mean([r[1] for r in sub]) * 100
                tv = [r[2] for r in sub if r[2] is not None]
                tbs = (np.mean(tv) * 100) if tv else float("nan")
                print(f"  {b:>5}{len(sub):>8}{ah:>9.1f}{tbs:>8.1f}{len(tv):>7}")

        print(f"\n{'#'*70}\n#  CONFIRMATION-COUNT OUTCOME STUDY\n#  universe={len(universe)}  "
              f"enrichable signals={n_signals:,}\n#  absHit%=close-to-close directional; "
              f"tbs%=TP1-before-stop\n{'#'*70}")
        _report("OVERALL (all technical detectors pooled)", overall)
        for name in sorted(per_det, key=lambda k: -len(per_det[k])):
            if len(per_det[name]) >= 400:
                _report(f"detector: {name}", per_det[name])
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--min-bars", type=int, default=400)
    a = ap.parse_args()
    run(sample=a.sample, step=a.step, window=a.window, min_bars=a.min_bars)
