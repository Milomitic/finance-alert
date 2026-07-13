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
  3. Per detector — the TRADE-PLAYBOOK win-rate "tbs%": P(TP1 reached before the
     stop within the horizon), replicating frontend/src/lib/tradePlaybook.ts in
     Python and walking forward bars with HIGH/LOW. Measured (C2, 2026-05) as a
     candidate Probabilità base rate but DATA-REJECTED: tbs% clustered ~18-23%
     (NARROWER spread than absHit, range 5.8 vs 8.7) and is undefined for the 6
     detectors with no structural invalidation level. Kept as a DIAGNOSTIC only;
     --emit-map writes the absHit% base rate (wider spread + full coverage).

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
from app.signals.context import build_context
from app.signals.horizon import _PRIOR, classify_horizon
from app.signals.runner import detect_signals

_H_BY_HORIZON = {"short": H_SHORT, "medium": H_MED, "long": H_LONG}


def _detector_horizon(name: str) -> int:
    return _H_BY_HORIZON.get(_PRIOR.get(name, "medium"), H_MED)


# ── Trade-playbook geometry (mirror of frontend/src/lib/tradePlaybook.ts) ────
# Per-horizon: forward horizon H in trading days + the stop/target geometry we
# need (floor + tp1R + tp1Cap). `floor`/`tp1Cap` are ATR multiples; `tp1R` is an
# R-multiple. We only model TP1-before-stop, so tp2* are intentionally omitted.
STOP_CAP_ATR = 8.0
_PLAYBOOK_HZ: dict[str, dict[str, float]] = {
    "short":  {"H": 10, "floor": 0.5, "tp1R": 4.0, "tp1Cap": 2.0},
    "medium": {"H": 30, "floor": 2.5, "tp1R": 2.0, "tp1Cap": 10.0},
    "long":   {"H": 63, "floor": 1.0, "tp1R": 3.0, "tp1Cap": 8.0},
}


def _trade_playbook_hit(
    s, i: int, m, *, highs: np.ndarray, lows: np.ndarray,
) -> float | None:
    """Replicate the Trade Playbook (tradePlaybook.ts buildPlaybook) and walk
    the bars forward to decide whether TP1 is reached BEFORE the stop within the
    horizon — a tradeable, path-based hit-rate.

    Returns:
      1.0  -> TP1 hit before the stop within H bars (WIN)
      0.0  -> stop hit first, both-in-one-candle (conservative stop-first), or
              neither hit within H (UNRESOLVED counts as NOT a win)
      None -> SKIP this signal (no usable structural level; the playbook itself
              returns null in that case, so it's excluded from the metric)
    """
    entry = float(s.closes[i])
    if not (entry > 0):
        return None

    inv = m.invalidation
    level = inv.get("level") if isinstance(inv, dict) else None
    if not (isinstance(level, (int, float)) and np.isfinite(level) and level > 0):
        return None  # no structural invalidation -> playbook returns null

    # ATR — same anchor the scan stores; fall back to a 2%-of-price proxy.
    ctx = build_context(s.df.iloc[: i + 1])
    atr = ctx.atr
    if atr is None or not np.isfinite(atr) or atr <= 0:
        atr = entry * 0.02

    hz = classify_horizon(m.name, m.chain)
    P = _PLAYBOOK_HZ.get(hz, _PLAYBOOK_HZ["medium"])
    H = int(P["H"])
    sign = 1 if m.tone == "bull" else -1

    struct_dist = abs(entry - level)
    R = min(max(struct_dist, P["floor"] * atr), STOP_CAP_ATR * atr)
    if R <= 0:
        return None
    stop = entry - sign * R
    d1 = min(P["tp1R"] * R, P["tp1Cap"] * atr)
    target = entry + sign * d1

    n = len(s.closes)
    last = min(i + H, n - 1)
    for k in range(i + 1, last + 1):
        hi = highs[k]
        lo = lows[k]
        if sign > 0:  # long: TP up, stop down
            hit_tp = hi >= target
            hit_stop = lo <= stop
        else:         # short: TP down, stop up
            hit_tp = lo <= target
            hit_stop = hi >= stop
        if hit_tp and hit_stop:
            return 0.0  # both in one candle -> conservative stop-first => LOSS
        if hit_tp:
            return 1.0
        if hit_stop:
            return 0.0
    return 0.0  # unresolved within H -> NOT a win


def run(*, sample: int, step: int, window: int, min_bars: int,
        emit_map: bool = False, map_version: str = "1") -> None:
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

        # Accumulators. Per detector, one tuple per fired signal:
        #   (dir_excess, confidence, abs_hit, tbs)
        # where tbs (trade-playbook TP1-before-stop, 1/0) is None when the
        # signal had no usable structural level (excluded from the tbs aggregate).
        per_det: dict[str, list[tuple[float, int, float, float | None]]] = defaultdict(list)
        n_calls = 0
        n_signals = 0

        for sidx, s in enumerate(universe):
            df = s.df
            c = s.closes
            n = len(c)
            highs = df["high"].to_numpy(dtype="float64")
            lows = df["low"].to_numpy(dtype="float64")
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
                    # ABSOLUTE directional hit ("di accadimento"): did the move
                    # go the signalled way, regardless of the market? This is
                    # the basis for Probabilità (vs market-neutral = skill edge).
                    abs_hit = 1.0 if ((m.tone == "bull" and fwd > 0)
                                      or (m.tone == "bear" and fwd < 0)) else 0.0
                    # TRADE-PLAYBOOK hit ("TP1 before stop within H", path-based):
                    # the tradeable win-rate we want as the Probabilità base rate.
                    # None when the signal has no usable structural level (excluded
                    # from the tbs aggregate, but the row still carries abs_hit).
                    tbs = _trade_playbook_hit(s, i, m, highs=highs, lows=lows)
                    per_det[m.name].append((dir_excess, int(m.strength), abs_hit, tbs))
                    n_signals += 1
            if (sidx + 1) % 25 == 0:
                logger.info(f"[detector-outcomes] {sidx + 1}/{len(universe)} stocks, "
                            f"{n_signals:,} signals so far")

        logger.info(f"[detector-outcomes] {n_calls:,} detect calls, {n_signals:,} signals")

        print(f"\n{'#'*78}\n#  DETECTOR-LEVEL OUTCOME STUDY (the conjunction)")
        print(f"#  universe={len(universe)}  detect_calls={n_calls:,}  signals={n_signals:,}")
        print("#  absHit% = close-to-close directional hit (flat ~50%); tbs% =")
        print("#  trade-playbook TP1-before-stop within horizon (the path-based,")
        print(f"#  tradeable win-rate — the proposed Probabilita base rate)\n{'#'*78}")
        print(f"\n{'detector':<24}{'n':>7}{'absHit%':>9}{'tbs%':>8}{'tbsN':>7}"
              f"{'mnHit%':>8}{'mnEdge%':>9}{'horiz':>7}")
        print("-" * 78)
        base_rates: dict[str, dict] = {}
        for name in sorted(per_det, key=lambda k: -len(per_det[k])):
            arr = per_det[name]
            if len(arr) < 30:
                continue
            de = np.array([a[0] for a in arr])
            abs_hit = float(np.mean([a[2] for a in arr])) * 100   # close-to-close hit
            mn_hit = float((de > 0).mean()) * 100                 # market-neutral hit
            edge = float(de.mean()) * 100                         # market-neutral edge
            # Trade-playbook win-rate over the rows that had a usable structural
            # level (tbs is None when buildPlaybook would have returned null).
            tbs_vals = [a[3] for a in arr if a[3] is not None]
            tbs_n = len(tbs_vals)
            tbs = float(np.mean(tbs_vals)) * 100 if tbs_n else float("nan")
            h = _detector_horizon(name)
            # base_rate = absHit% (close-to-close directional hit). We MEASURED
            # the trade-playbook tbs% as a candidate (C2, 2026-05) but data
            # rejected it: tbs clustered ~18-23% (NARROWER spread than absHit,
            # range 5.8 vs 8.7) and was undefined for 6/14 detectors (no
            # structural level). So absHit stays the Probabilità base rate;
            # tbs_rate is kept only as a diagnostic.
            base_rates[name] = {"base_rate": round(abs_hit),
                                "tbs_rate": (round(tbs, 1) if tbs_n else None),
                                "tbs_n": tbs_n,
                                "close_to_close_hit": round(abs_hit, 1),
                                "horizon_days": h,
                                "n": len(arr), "mkt_neutral_hit": round(mn_hit, 1),
                                "mkt_neutral_edge_pct": round(edge, 3)}
            tbs_s = f"{tbs:>8.1f}" if tbs_n else f"{'n/a':>8}"
            print(f"{name:<24}{len(arr):>7}{abs_hit:>9.1f}{tbs_s}{tbs_n:>7}"
                  f"{mn_hit:>8.1f}{edge:>+9.2f}{h:>6}d")

        # Pooled: does CURRENT confidence predict the outcome?
        all_pairs = [p for arr in per_det.values() for p in arr]
        print(f"\n{'='*78}\n  IS CURRENT `confidence` PREDICTIVE?  (pooled, n={len(all_pairs):,})\n{'='*78}")
        print(f"  {'confidence band':<18}{'n':>8}{'absHit%':>9}{'mnHit%':>8}{'mnEdge%':>9}")
        bands = [(0, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
        for lo, hi in bands:
            sub = [(de, ah) for de, conf, ah, _tbs in all_pairs if lo <= conf < hi]
            if not sub:
                continue
            de_a = np.array([s[0] for s in sub])
            ah_a = np.array([s[1] for s in sub])
            print(f"  [{lo:>3},{hi:>3})        {len(sub):>8}{ah_a.mean()*100:>9.1f}"
                  f"{(de_a>0).mean()*100:>8.1f}{de_a.mean()*100:>+9.2f}")
        print("\n  If absHit/mnHit RISES with the confidence band, the current score")
        print("  is predictive; if FLAT, it's pattern-strength not probability —")
        print("  which is exactly why we split it into Forza + Probabilita.")
        print("\n  Legend: absHit% = close-to-close directional hit — the Probabilita")
        print("  base rate (--emit-map writes it). tbs% = trade-playbook TP1-before-")
        print("  stop within horizon (DIAGNOSTIC only): measured as a candidate base")
        print("  rate but REJECTED — narrower spread than absHit + undefined for the")
        print("  6 detectors with no structural level. Probabilita stays on absHit.\n")

        if emit_map:
            import json
            from pathlib import Path

            payload = {
                "version": map_version,
                "generated_by": "app.scripts.signal_detector_outcomes",
                # base_rate per detector = round(absHit), the close-to-close
                # directional hit-rate. The C2 candidate (trade-playbook
                # TP1-before-stop) was REJECTED by the data (narrower spread,
                # undefined for 6/14 detectors) — tbs_rate/tbs_n stay only as
                # diagnostics. This label was stale ("trade_playbook_tp1_
                # before_stop") until 2026-07-04 while the VALUE was always
                # absHit; no consumer reads it, but labels shouldn't lie.
                "base_rate_metric": "close_to_close_abs_hit",
                "universe_stocks": len(universe),
                "signals": int(n_signals),
                "horizons": {"short": H_SHORT, "medium": H_MED, "long": H_LONG},
                "detectors": base_rates,
                # Per-factor adjustment points (raw -> +/- pts). Empty in v1: the
                # marginal-factor study showed mostly-flat effects, so the
                # detector base rate dominates. Populated in a follow-up.
                "factor_adjustments": {},
            }
            out_path = Path(__file__).resolve().parents[1] / "data" / "signal_calibration.json"
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"  [emit-map] wrote {out_path} "
                  f"({len(base_rates)} detectors, {n_signals:,} signals)\n")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--step", type=int, default=42)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--min-bars", type=int, default=1000)
    ap.add_argument("--emit-map", action="store_true",
                    help="write app/data/signal_calibration.json from the base rates")
    ap.add_argument("--map-version", type=str, default="1")
    args = ap.parse_args()
    run(sample=args.sample, step=args.step, window=args.window, min_bars=args.min_bars,
        emit_map=args.emit_map, map_version=args.map_version)
