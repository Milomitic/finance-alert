"""Does signal skill depend on the MARKET REGIME? (validates roadmap #8)

For each detector, replay 10y no-look-ahead (reusing signal_factor_outcomes'
universe + market-neutral machinery) and split every fired signal by the regime
at its trigger bar (close vs causal EMA200: bull = above, bear = below). Then
compare the detector's skill in bull vs bear regimes.

CRITICAL design choice: the metric is the MARKET-NEUTRAL hit (share of signals
whose tone-signed excess-over-universe-mean is positive), NOT the absolute hit.
Absolute hit is confounded by beta — bull signals "work" in bull regimes simply
because the whole market rose. Market-neutral strips that out, so a regime
difference here is genuine conditional SKILL, not direction.

Guards against fooling ourselves:
  - OOS split: older `1-holdout` of dates = TRAIN, newer = HOLDOUT. A regime
    effect must keep the SAME SIGN in the holdout to count.
  - Wilson 95% CIs on each regime's hit rate; the bull-vs-bear delta is only
    "real" if the CIs separate.
  - Per (detector, regime) min-sample floor.

Dumps a machine-readable JSON (per detector x regime x period) for downstream
adversarial verification + (only if validated) a calibration change.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.regime_conditioned_outcomes --sample 300 --step 3
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from loguru import logger

from app.scripts.signal_detector_outcomes import _detector_horizon
from app.scripts.signal_factor_outcomes import (
    H_SHORT,
    _load_universe,
    _universe_mean_fwd,
)
from app.signals.runner import detect_signals

_MIN_CELL = 100   # min signals per (detector, regime) to report a rate
_Z = 1.96


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values)
    acc = values[0]
    out[0] = acc
    for i in range(1, len(values)):
        acc = alpha * values[i] + (1 - alpha) * acc
        out[i] = acc
    return out


def _wilson(hits: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    z2 = _Z * _Z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (_Z * np.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def run(*, sample: int, step: int, window: int, min_bars: int, holdout_frac: float,
        out: str = "app/data/regime_conditioned_study.json") -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
        logger.info(f"[regime] {len(universe)} stocks")
        if not universe:
            print("No eligible stocks.")
            return
        umean = _universe_mean_fwd(universe)
        date_to_idx = umean["_date_to_idx"]

        all_dates = sorted({d for s in universe for d in s.dates})
        cutoff = all_dates[int(len(all_dates) * (1 - holdout_frac))]
        logger.info(f"[regime] OOS cutoff date = {cutoff} (holdout = newest {holdout_frac:.0%})")

        # (detector, regime, period) -> list[mkt_neutral_hit (1/0)]
        per: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        n_signals = 0
        for sidx, s in enumerate(universe):
            df = s.df
            c = s.closes
            n = len(c)
            ema200 = _ema(c, 200)
            for i in range(window, n - H_SHORT, step):
                win = df.iloc[i - window:i + 1].reset_index(drop=True)
                try:
                    matches = detect_signals(win)
                except Exception:  # noqa: BLE001
                    continue
                if not matches:
                    continue
                di = date_to_idx.get(s.dates[i])
                regime = "bull" if c[i] > ema200[i] else "bear"
                period = "holdout" if s.dates[i] >= cutoff else "train"
                for m in matches:
                    h = _detector_horizon(m.name)
                    if i + h >= n or c[i] <= 0:
                        continue
                    mean = umean[h][di] if di is not None else np.nan
                    if not np.isfinite(mean):
                        continue
                    fwd = c[i + h] / c[i] - 1.0
                    dir_excess = (fwd - mean) if m.tone == "bull" else -(fwd - mean)
                    per[(m.name, regime, period)].append(1 if dir_excess > 0 else 0)
                    n_signals += 1
            if (sidx + 1) % 25 == 0:
                logger.info(f"[regime] {sidx + 1}/{len(universe)} stocks, {n_signals:,} signals")

        detectors = sorted({k[0] for k in per})
        out: dict[str, dict] = {}
        print(f"\n{'#'*92}\n#  REGIME-CONDITIONED SKILL  (market-neutral hit; bull/bear = close vs EMA200)")
        print(f"#  universe={len(universe)}  signals={n_signals:,}  OOS cutoff={cutoff}\n{'#'*92}")
        print(f"{'detector':<22}{'bull%':>7}{'bear%':>7}{'Δ(b-b)':>8}{'CIsep':>6}"
              f"{'nB':>7}{'nb':>7}{'OOSΔ':>7}{'OOSsign':>8}")
        print("-" * 92)
        for det in detectors:
            def cell(reg, period=None):
                if period:
                    arr = per.get((det, reg, period), [])
                else:
                    arr = per.get((det, reg, "train"), []) + per.get((det, reg, "holdout"), [])
                return arr
            bull, bear = cell("bull"), cell("bear")
            if len(bull) < _MIN_CELL or len(bear) < _MIN_CELL:
                continue
            pB, pb = 100 * np.mean(bull), 100 * np.mean(bear)
            loB, hiB = _wilson(int(sum(bull)), len(bull))
            lob, hib = _wilson(int(sum(bear)), len(bear))
            ci_sep = (loB * 100 > hib * 100) or (lob * 100 > hiB * 100)
            # OOS: delta sign in holdout vs train
            bt, bbt = cell("bull", "train"), cell("bear", "train")
            bh, bbh = cell("bull", "holdout"), cell("bear", "holdout")
            d_train = (np.mean(bt) - np.mean(bbt)) if bt and bbt else float("nan")
            d_hold = (np.mean(bh) - np.mean(bbh)) if bh and bbh else float("nan")
            oos_sign = (np.isfinite(d_train) and np.isfinite(d_hold)
                        and np.sign(d_train) == np.sign(d_hold) and d_train != 0)
            print(f"{det:<22}{pB:>7.1f}{pb:>7.1f}{pB - pb:>+8.1f}{('YES' if ci_sep else '·'):>6}"
                  f"{len(bull):>7}{len(bear):>7}{100 * d_hold:>+7.1f}{('same' if oos_sign else 'FLIP'):>8}")
            out[det] = {
                "bull_hit": round(pB, 2), "bear_hit": round(pb, 2),
                "delta": round(pB - pb, 2), "ci_separated": bool(ci_sep),
                "n_bull": len(bull), "n_bear": len(bear),
                "delta_train": round(100 * d_train, 2) if np.isfinite(d_train) else None,
                "delta_holdout": round(100 * d_hold, 2) if np.isfinite(d_hold) else None,
                "oos_sign_stable": bool(oos_sign),
            }

        out_path = Path(out)
        out_path.write_text(json.dumps(out, indent=2))
        print(f"\n[dump] {out_path}  ({len(out)} detectors)")
        print("\nA regime effect is CREDIBLE only if: CIsep=YES AND OOSsign=same AND "
              "|Δ| material. Anything else = noise → ship the null (no per-regime "
              "calibration). Market-neutral metric → a real Δ is conditional SKILL, not beta.")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--min-bars", type=int, default=400)
    ap.add_argument("--holdout-frac", type=float, default=0.30)
    ap.add_argument("--out", type=str, default="app/data/regime_conditioned_study.json")
    a = ap.parse_args()
    run(sample=a.sample, step=a.step, window=a.window, min_bars=a.min_bars,
        holdout_frac=a.holdout_frac, out=a.out)
