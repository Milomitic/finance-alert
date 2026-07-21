"""Outcome-based calibration study for SIGNAL-CONFIDENCE factors.

PURPOSE
═══════
The confidence model assigns each signal a 0-100 score by shaping per-factor
"strength" values (candle body/range, breakout %, gap %, RSI-divergence
amplitude, ...) onto [0,1] curves and combining them. The open question this
script answers EMPIRICALLY:

    For each factor, does a HIGHER raw value actually correspond to a better
    realised forward outcome — and WHERE are the breakpoints?

That is the difference between calibrating a curve to RARITY (the 90th
percentile of observed strength) versus to PREDICTIVE VALUE (the strength
level above which the signal genuinely tends to work). We want the latter:
confidence ≈ expected hit-rate, so the truly-strong "monster" signals land at
the top of the scale because they EARN it, not because they're unusual.

METHOD (mirrors entry_ic_report.py's no-look-ahead discipline)
══════════════════════════════════════════════════════════════
  • Re-derive signals by running the PRODUCTION event extractors
    (app.signals.events / candles) over each stock's full 10y OHLCV — so the
    measured magnitudes are EXACTLY what the live code computes, no re-impl.
  • No look-ahead: extractor indicators (EMA/RSI/ATR/BB) at bar i are causal
    (depend only on bars ≤ i); computing on the full series then sampling at i
    equals recomputing on ohlcv[:i+1]. Pivot-confirmed events (RSI/MACD/hidden
    divergence) are only KNOWN pivot_w bars after the pivot bar, so we measure
    the forward return from bar i+pivot_w, not the pivot bar.
  • Forward return = close-to-close pct change over h trading days from the
    bar the signal is knowable on.
  • MARKET-NEUTRAL: we subtract the universe's mean forward return on that
    same calendar date, so "edge" is excess vs the market that day — a gap-up
    in a +3% tape shouldn't be credited for the tape.
  • DIRECTIONAL factors (breakout, gap, divergence, expansion, candle, adx,
    rsi-extreme) → report HIT-RATE (% of events whose market-neutral move went
    the signalled way) + mean directional edge, bucketed by raw magnitude.
  • MAGNITUDE-ONLY factors (volume ratio, squeeze tightness — directionless
    confirmers) → report mean ABSOLUTE excess move per bucket: their job is to
    predict move SIZE, not direction.

OUTPUT
══════
Per factor: a bucketed table (raw-value range → n / hit-rate or |move| / edge /
monotonic flag) and SUGGESTED ANCHORS — the raw values at which the directional
hit-rate first crosses 52% / 56% / 60% (interpolated), which become the curve's
0.45 / 0.75 / 0.88 breakpoints downstream. This is the grounding the per-factor
confidence curves are built from.

This is a read-only measurement instrument: it imports the production
extractors but writes nothing and touches no production tables.

USAGE
═════
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.signal_factor_outcomes
      --min-bars N     require >= N bars of history (default 1000 ≈ 4y)
      --sample N       use only the first N eligible stocks (quick smoke run)
      --buckets N      quantile buckets per factor (default 6)
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import bindparam, text

from app.core.db import SessionLocal
from app.signals.candles import extract_candle_reversal
from app.signals.events import (
    extract_adx_trend,
    extract_bollinger,
    extract_breakout,
    extract_gap,
    extract_macd_divergence,
    extract_rsi_divergence,
    extract_rsi_extreme,
    extract_volume_spike,
)

# Horizon (trading days) used to judge each factor, from the detector's
# natural horizon prior (app/signals/horizon.py): short≈5, medium≈21, long≈63.
H_SHORT, H_MED, H_LONG = 5, 21, 63
_ALL_H = (H_SHORT, H_MED, H_LONG)
# pivot_w used by the divergence extractors — the lag before a pivot is
# confirmed and the signal becomes knowable.
_PIVOT_W = 5


@dataclass
class _Stock:
    stock_id: int
    ticker: str
    df: pd.DataFrame          # columns: date, open, high, low, close, volume
    closes: np.ndarray
    dates: list[str]


@dataclass
class _Obs:
    """One re-derived historical signal occurrence."""
    factor: str
    raw: float
    direction: str | None     # "bull" | "bear" | None (magnitude-only)
    entry_i: int              # bar index the signal is KNOWABLE on
    stock_idx: int            # index into the universe list


# factor → (extractor callable, event_type filter, horizon, pivot_lag, mode)
#   mode: "dir" = directional hit-rate; "mag" = directionless move-size.
# Some extractors emit several event types; we filter by `etype`.
def _load_universe(db, *, min_bars: int, sample: int | None) -> list[_Stock]:
    rows = db.execute(
        text(
            """
            SELECT s.id, s.ticker
            FROM stocks s
            WHERE (SELECT COUNT(*) FROM ohlcv_daily o WHERE o.stock_id = s.id) >= :mb
            ORDER BY s.id
            """
        ),
        {"mb": min_bars},
    ).all()
    if sample:
        rows = rows[:sample]
    ids = [r[0] for r in rows]
    ticker_by_id = {r[0]: r[1] for r in rows}
    if not ids:
        return []
    bars = db.execute(
        text(
            """
            SELECT stock_id, date, open, high, low, close, volume
            FROM ohlcv_daily
            WHERE stock_id IN :ids
            ORDER BY stock_id, date
            """
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    ).all()

    out: list[_Stock] = []
    cur_id: int | None = None
    rec: list[tuple] = []

    def _flush():
        if cur_id is None or len(rec) < min_bars:
            return
        df = pd.DataFrame(
            rec, columns=["date", "open", "high", "low", "close", "volume"]
        )
        df["date"] = df["date"].astype(str).str.slice(0, 10)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        out.append(
            _Stock(
                stock_id=cur_id,
                ticker=ticker_by_id.get(cur_id, str(cur_id)),
                df=df,
                closes=df["close"].to_numpy(dtype="float64"),
                dates=df["date"].tolist(),
            )
        )

    for sid, d, o, h, lo, c, v in bars:
        if sid != cur_id:
            _flush()
            cur_id = sid
            rec = []
        rec.append((d, o, h, lo, c, v))
    _flush()
    return out


def _universe_mean_fwd(universe: list[_Stock]) -> dict[int, np.ndarray]:
    """Per-calendar-date mean forward return across the whole universe, for
    each horizon. Returns {h: mean_array_indexed_by_global_calendar}, plus a
    shared date→idx map stored on the function via attribute for reuse."""
    all_dates: set[str] = set()
    for s in universe:
        all_dates.update(s.dates)
    cal = sorted(all_dates)
    date_to_idx = {d: i for i, d in enumerate(cal)}
    sums = {h: np.zeros(len(cal)) for h in _ALL_H}
    counts = {h: np.zeros(len(cal)) for h in _ALL_H}
    for s in universe:
        c = s.closes
        n = len(c)
        idxs = np.fromiter((date_to_idx[d] for d in s.dates), dtype=np.int64, count=n)
        for h in _ALL_H:
            if n <= h:
                continue
            base = c[:-h]
            with np.errstate(divide="ignore", invalid="ignore"):
                fwd = np.where(base > 0, c[h:] / base - 1.0, np.nan)
            di = idxs[:-h]
            ok = np.isfinite(fwd)
            np.add.at(sums[h], di[ok], fwd[ok])
            np.add.at(counts[h], di[ok], 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = {h: np.where(counts[h] > 0, sums[h] / counts[h], np.nan) for h in _ALL_H}
    mean["_date_to_idx"] = date_to_idx  # type: ignore[assignment]
    return mean


def _collect_observations(universe: list[_Stock]) -> list[_Obs]:
    """Run the production extractors over every stock and record one _Obs per
    qualifying event, with the entry index set to where the signal is knowable.
    """
    obs: list[_Obs] = []
    for sidx, s in enumerate(universe):
        df = s.df
        pos = {d: i for i, d in enumerate(s.dates)}

        def add(factor, events, *, mode_dir, lag=0, pos=pos, sidx=sidx):  # noqa: ANN001
            for e in events:
                i = pos.get(e.date)
                if i is None or e.magnitude is None:
                    continue
                entry = i + lag
                obs.append(
                    _Obs(
                        factor=factor,
                        raw=float(e.magnitude),
                        direction=(e.direction if mode_dir else None),
                        entry_i=entry,
                        stock_idx=sidx,
                    )
                )

        try:
            add("volume_breakout.breakout_strength", extract_breakout(df, lookback=20), mode_dir=True)
            add("gap.gap_size", extract_gap(df, min_pct=0.02), mode_dir=True)
            add("candle_reversal.candle_strength", extract_candle_reversal(df), mode_dir=True)
            add("oversold_reversal.rsi_extremity", extract_rsi_extreme(df), mode_dir=True)
            add("adx_confirmation.adx_strength", extract_adx_trend(df), mode_dir=True)
            # Divergences are pivot-confirmed → only knowable pivot_w bars later.
            add("rsi_divergence.divergence_amplitude",
                extract_rsi_divergence(df), mode_dir=True, lag=_PIVOT_W)
            add("macd_divergence.divergence_amplitude",
                extract_macd_divergence(df), mode_dir=True, lag=_PIVOT_W)
            # Bollinger: squeeze (tightness, directionless) + expansion (directional)
            bb = extract_bollinger(df)
            add("squeeze.tightness", [e for e in bb if e.type == "bb_squeeze"], mode_dir=False)
            add("squeeze.expansion_strength", [e for e in bb if e.type == "bb_expansion"], mode_dir=True)
            # Volume: directionless confirmer (predicts move size).
            add("volume_strength", extract_volume_spike(df), mode_dir=False)
            # di_spread from adx payload (separate factor).
            for e in extract_adx_trend(df):
                i = pos.get(e.date)
                if i is None:
                    continue
                pdi = e.payload.get("plus_di")
                mdi = e.payload.get("minus_di")
                if pdi is None or mdi is None:
                    continue
                obs.append(_Obs("adx_confirmation.di_spread", float(abs(pdi - mdi)),
                                e.direction, i, sidx))
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[factor-outcomes] {s.ticker} extract failed: {exc}")
            continue
    return obs


def _attach_outcomes(
    obs: list[_Obs], universe: list[_Stock], umean: dict, horizon: int,
) -> pd.DataFrame:
    """For each obs compute the market-neutral DIRECTIONAL excess forward
    return at `horizon`. Returns a DataFrame: factor, raw, dir_excess, abs_excess,
    direction."""
    date_to_idx = umean["_date_to_idx"]
    mh = umean[horizon]
    recs = []
    for o in obs:
        s = universe[o.stock_idx]
        c = s.closes
        i = o.entry_i
        if i < 0 or i + horizon >= len(c) or c[i] <= 0:
            continue
        fwd = c[i + horizon] / c[i] - 1.0
        di = date_to_idx.get(s.dates[i])
        m = mh[di] if di is not None else np.nan
        if not np.isfinite(m):
            continue
        excess = fwd - m
        if o.direction == "bear":
            dir_excess = -excess
        else:  # bull or None → treat as long-side reading
            dir_excess = excess
        recs.append((o.factor, o.raw, dir_excess, abs(excess), o.direction or "none"))
    return pd.DataFrame(recs, columns=["factor", "raw", "dir_excess", "abs_excess", "direction"])


_DIR_FACTORS = {
    "volume_breakout.breakout_strength", "gap.gap_size",
    "candle_reversal.candle_strength", "oversold_reversal.rsi_extremity",
    "adx_confirmation.adx_strength", "adx_confirmation.di_spread",
    "rsi_divergence.divergence_amplitude", "macd_divergence.divergence_amplitude",
    "squeeze.expansion_strength",
}
_MAG_FACTORS = {"squeeze.tightness", "volume_strength"}

# Which horizon to judge each factor at (its detector's natural horizon).
_FACTOR_H = {
    "volume_breakout.breakout_strength": H_MED,
    "gap.gap_size": H_SHORT,
    "candle_reversal.candle_strength": H_SHORT,
    "oversold_reversal.rsi_extremity": H_MED,
    "adx_confirmation.adx_strength": H_LONG,
    "adx_confirmation.di_spread": H_LONG,
    "rsi_divergence.divergence_amplitude": H_MED,
    "macd_divergence.divergence_amplitude": H_MED,
    "squeeze.expansion_strength": H_MED,
    "squeeze.tightness": H_MED,
    "volume_strength": H_MED,
}


def _report_factor(name: str, df: pd.DataFrame, n_buckets: int) -> None:
    sub = df[df["factor"] == name]
    sub = sub[np.isfinite(sub["raw"]) & np.isfinite(sub["dir_excess"])]
    n = len(sub)
    if n < n_buckets * 20:
        print(f"\n{name}: only {n} obs — too few to bucket, skipping.")
        return
    directional = name in _DIR_FACTORS
    try:
        sub = sub.copy()
        sub["bucket"] = pd.qcut(sub["raw"].rank(method="first"), n_buckets, labels=False)
    except ValueError:
        print(f"\n{name}: cannot bucket (degenerate distribution).")
        return

    print(f"\n{'='*78}\n  {name}    [{'directional hit-rate' if directional else 'move-size'}]"
          f"  n={n:,}  horizon={_FACTOR_H.get(name,'?')}d\n{'='*78}")
    print(f"  {'bucket raw range':<26}{'n':>7}{'hit%':>8}{'edge%':>9}{'|move|%':>9}")
    rows = []
    for b in range(n_buckets):
        g = sub[sub["bucket"] == b]
        if g.empty:
            continue
        lo, hi = g["raw"].min(), g["raw"].max()
        hit = float((g["dir_excess"] > 0).mean()) * 100
        edge = float(g["dir_excess"].mean()) * 100
        mv = float(g["abs_excess"].mean()) * 100
        rows.append((lo, hi, len(g), hit, edge, mv))
        print(f"  [{lo:>9.4f},{hi:>9.4f}]{len(g):>7}{hit:>8.1f}{edge:>+9.2f}{mv:>9.2f}")

    # Monotonicity of the judged metric across buckets.
    series = [r[3] if directional else r[5] for r in rows]
    mono = all(series[i] <= series[i + 1] + 1e-9 for i in range(len(series) - 1))
    print(f"  monotonic({'hit' if directional else '|move|'} rises with raw): {mono}")

    if directional:
        # Suggested anchors: interpolate the raw value where hit% crosses targets.
        _suggest_anchors(rows)


def _suggest_anchors(rows: list[tuple]) -> None:
    """rows: (lo, hi, n, hit, edge, mv) per bucket. Find the raw value (bucket
    high edge) where hit-rate first crosses 52 / 56 / 60%."""
    targets = [(52, "0.45"), (56, "0.75"), (60, "0.88")]
    mids = [( (r[0] + r[1]) / 2, r[3]) for r in rows]
    out = []
    for thr, curve in targets:
        anchor = None
        for j in range(1, len(mids)):
            x0, y0 = mids[j - 1]
            x1, y1 = mids[j]
            if (y0 < thr <= y1) and y1 != y0:
                anchor = x0 + (x1 - x0) * (thr - y0) / (y1 - y0)
                break
        if anchor is None and mids and mids[-1][1] >= thr:
            anchor = mids[-1][0]
        out.append(f"hit>={thr}% -> curve {curve} @ raw~{anchor:.4f}" if anchor is not None
                   else f"hit>={thr}%: never reached")
    print("  ANCHORS: " + " | ".join(out))


def run(*, min_bars: int, sample: int | None, n_buckets: int) -> None:
    db = SessionLocal()
    try:
        logger.info(f"[factor-outcomes] loading universe (min_bars={min_bars}) ...")
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
        logger.info(f"[factor-outcomes] {len(universe)} stocks")
        if not universe:
            print("No eligible stocks.")
            return
        logger.info("[factor-outcomes] computing universe mean forward returns ...")
        umean = _universe_mean_fwd(universe)
        logger.info("[factor-outcomes] re-deriving historical signals ...")
        obs = _collect_observations(universe)
        logger.info(f"[factor-outcomes] {len(obs):,} signal occurrences re-derived")

        # Group obs by their judged horizon so each factor is scored at its own h.
        by_h: dict[int, list[_Obs]] = defaultdict(list)
        for o in obs:
            by_h[_FACTOR_H.get(o.factor, H_MED)].append(o)

        frames = []
        for h, lst in by_h.items():
            frames.append(_attach_outcomes(lst, universe, umean, h))
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if df.empty:
            print("No outcomes attached.")
            return

        print(f"\n{'#'*78}\n#  SIGNAL-FACTOR OUTCOME STUDY")
        print(f"#  universe={len(universe)} stocks  obs={len(df):,}  "
              f"market-neutral excess fwd returns\n{'#'*78}")

        order = [
            "candle_reversal.candle_strength",
            "gap.gap_size",
            "volume_breakout.breakout_strength",
            "squeeze.expansion_strength",
            "squeeze.tightness",
            "rsi_divergence.divergence_amplitude",
            "macd_divergence.divergence_amplitude",
            "oversold_reversal.rsi_extremity",
            "adx_confirmation.adx_strength",
            "adx_confirmation.di_spread",
            "volume_strength",
        ]
        for name in order:
            _report_factor(name, df, n_buckets)
        print("\nLegend: hit% = market-neutral move went the signalled way;")
        print("        edge% = mean directional excess fwd return; |move|% = mean")
        print("        absolute excess move. ANCHORS map hit-rate crossings to the")
        print("        concave-curve breakpoints (0.45/0.75/0.88).\n")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-bars", type=int, default=1000)
    ap.add_argument("--sample", type=int, default=None)
    ap.add_argument("--buckets", type=int, default=6)
    args = ap.parse_args()
    run(min_bars=args.min_bars, sample=args.sample, n_buckets=args.buckets)
