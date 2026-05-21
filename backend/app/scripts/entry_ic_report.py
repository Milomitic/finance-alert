"""Information-Coefficient (IC) report for candidate scoring signals.

PURPOSE
═══════
Before adding ANY signal to the scoring system — and especially before
building the "Entry Timing" sleeve — we must know which signals
actually predict forward returns ON THIS UNIVERSE. This script is a
read-only measurement instrument: it touches no production code, it
just reads `ohlcv_daily`, computes each candidate signal at a grid of
historical observation dates, pairs it with the realised forward
return, and reports the predictive power.

It answers, per signal × horizon:
  • rank-IC (mean)      — average per-date Spearman corr(signal, fwd ret)
  • rank-IC (std)       — dispersion of that correlation across dates
  • IR = mean/std       — information ratio (IC stability)
  • decile spread       — mean fwd return of top-decile minus bottom-
                          decile (does "higher signal = higher return"
                          actually hold, and monotonically?)
  • hit rate            — % of dates where the IC had the expected sign

METHODOLOGY (why these choices)
═══════════════════════════════
  • Per-date IC then averaged (NOT one pooled correlation over all
    obs): pooled IC is inflated by autocorrelation — the same stock's
    consecutive observations aren't independent. Averaging per-date
    cross-sections is the standard quant approach (Grinold-Kahn).
  • Monthly observation grid (every ~21 trading days): daily obs are
    ~95% autocorrelated and add no independent information while
    multiplying compute. Monthly gives ~120 quasi-independent cross-
    sections over 10 years.
  • No look-ahead: every signal at date t uses ONLY closes/volumes up
    to and including t; the forward return looks at t+h. Indicators
    are computed on the FULL series then sampled at t, which is
    equivalent to (and far faster than) recomputing per-date windows.
  • Forward return = simple close-to-close pct change over h trading
    days. Dividend adjustment is ignored (yfinance closes here are
    raw); over 5-63 day windows the dividend distortion is < noise.

USAGE
═════
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.entry_ic_report
    # options:
    #   --us-only         restrict to country='US' (default: all)
    #   --min-bars N       require >= N bars of history (default 800)
    #   --obs-step N       trading-days between observation dates (default 21)

OUTPUT
══════
A plain-text table to stdout. Higher |IC| and |IR| = stronger signal.
As a rule of thumb in single-name equity: |IC| ~0.03-0.05 is useful,
~0.05-0.08 is strong, >0.10 is rare/suspicious. IR > 0.5 means the
edge is reasonably stable across regimes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from app.core.db import SessionLocal
from app.indicators.ema import ema as ema_indicator
from app.indicators.rsi import rsi as rsi_indicator


# Forward-return horizons in trading days: ~1 week, ~1 month, ~1 quarter.
_HORIZONS = (5, 21, 63)
# Deciles for the spread analysis.
_N_BUCKETS = 10


@dataclass
class _StockSeries:
    stock_id: int
    ticker: str
    closes: pd.Series   # indexed 0..N-1, chronological
    volumes: pd.Series
    dates: list[str]    # ISO date per bar position (same length as closes)


def _load_universe(db, *, us_only: bool, min_bars: int) -> list[_StockSeries]:
    """Load full close+volume series per stock with >= min_bars history.

    One query for the eligible stock ids, then one bulk query for all
    bars ordered by (stock_id, date). Building per-stock Series from a
    single sorted result avoids N round-trips.
    """
    where = "WHERE 1=1"
    if us_only:
        where += " AND s.country = 'US'"
    rows = db.execute(
        text(
            f"""
            SELECT s.id, s.ticker
            FROM stocks s
            {where}
            AND (SELECT COUNT(*) FROM ohlcv_daily o WHERE o.stock_id = s.id)
                >= :min_bars
            ORDER BY s.id
            """
        ),
        {"min_bars": min_bars},
    ).all()
    ids = [r[0] for r in rows]
    ticker_by_id = {r[0]: r[1] for r in rows}
    if not ids:
        return []

    # Bulk-load every bar for the eligible ids in one sorted pass.
    bars = db.execute(
        text(
            """
            SELECT stock_id, date, close, volume
            FROM ohlcv_daily
            WHERE stock_id IN :ids
            ORDER BY stock_id, date
            """
        ).bindparams(__import__("sqlalchemy").bindparam("ids", expanding=True)),
        {"ids": ids},
    ).all()

    out: list[_StockSeries] = []
    # Group consecutive rows by stock_id (input is ordered by stock_id).
    cur_id: int | None = None
    cur_close: list[float] = []
    cur_vol: list[float] = []
    cur_dates: list[str] = []

    def _flush():
        if cur_id is None or len(cur_close) < min_bars:
            return
        out.append(
            _StockSeries(
                stock_id=cur_id,
                ticker=ticker_by_id.get(cur_id, str(cur_id)),
                closes=pd.Series(cur_close, dtype="float64").reset_index(drop=True),
                volumes=pd.Series(cur_vol, dtype="float64").reset_index(drop=True),
                dates=list(cur_dates),
            )
        )

    for sid, d, close, vol in bars:
        if sid != cur_id:
            _flush()
            cur_id = sid
            cur_close = []
            cur_vol = []
            cur_dates = []
        cur_close.append(float(close) if close is not None else np.nan)
        cur_vol.append(float(vol) if vol is not None else np.nan)
        cur_dates.append(str(d)[:10])
    _flush()
    return out


def _compute_signals(s: _StockSeries) -> pd.DataFrame:
    """Compute every candidate signal as a FULL series (one value per
    bar). Sampling happens later at the observation grid. Returns a
    DataFrame indexed like the closes, one column per signal.

    Signals fall into two families:
      QUALITY / TREND (sleeve-1 flavour) — already in the momentum
        pillar; included so we can compare their IC against the new
        entry signals on the same footing.
      ENTRY / TIMING (sleeve-2 candidates) — the new signals we're
        evaluating for inclusion.
    """
    c = s.closes
    v = s.volumes
    n = len(c)
    df = pd.DataFrame(index=c.index)

    # ── EMAs + trend stack ──────────────────────────────────────────
    ema20 = ema_indicator(c, 20)
    ema50 = ema_indicator(c, 50)
    ema200 = ema_indicator(c, 200)
    df["px_vs_ema200"] = (c - ema200) / ema200
    df["trend_stack"] = (
        (c > ema20).astype(float)
        + (ema20 > ema50).astype(float)
        + (ema50 > ema200).astype(float)
    )

    # ── Momentum family ─────────────────────────────────────────────
    # 12-1 (skip the last ~21 days): close[t-21] / close[t-273].
    df["mom_12_1"] = c.shift(21) / c.shift(273) - 1.0
    df["mom_90d"] = c / c.shift(63) - 1.0
    df["mom_30d"] = c / c.shift(21) - 1.0  # short-term reversal candidate

    # ── RSI(14) ─────────────────────────────────────────────────────
    rsi14 = rsi_indicator(c, 14)
    df["rsi14"] = rsi14
    # Oversold-bounce hypothesis: low RSI in an uptrend → entry. As a
    # continuous signal we encode "distance below 50, capped" so the
    # IC sign tells us whether oversold-buying actually pays here.
    df["rsi_below_50"] = (50.0 - rsi14).clip(lower=0)

    # ── Distance from 52-week high ───────────────────────────────────
    roll_high_252 = c.rolling(252, min_periods=120).max()
    df["dist_52w_high"] = c / roll_high_252 - 1.0  # 0 = at high, <0 below

    # ── 60-day breakout flag ─────────────────────────────────────────
    roll_high_60 = c.rolling(60, min_periods=40).max()
    # New 60-day high today (within 0.5%): a base breakout.
    df["breakout_60d"] = (c >= roll_high_60 * 0.995).astype(float)

    # ── Volume confirmation ──────────────────────────────────────────
    vol_avg20 = v.rolling(20, min_periods=10).mean()
    df["vol_ratio"] = v / vol_avg20

    # ── Volatility contraction (Bollinger-width proxy) ───────────────
    # Lower width = consolidation/coil → often precedes a move. We test
    # whether *contracted* volatility predicts higher forward return.
    sma20 = c.rolling(20, min_periods=20).mean()
    std20 = c.rolling(20, min_periods=20).std()
    df["bb_width"] = (4.0 * std20) / sma20  # (upper-lower)/mid = 4σ/mean
    # Negative so "more contracted = higher signal" (consistent
    # higher-is-better orientation for the IC sign read).
    df["bb_contraction"] = -df["bb_width"]

    # ── Composite entry candidate: pullback-in-uptrend ───────────────
    # Uptrend (stack >= 2) AND RSI in the 35-50 buy-the-dip band AND
    # within 12% of the 52w high (not a broken name). Binary flag.
    uptrend = df["trend_stack"] >= 2
    rsi_band = (rsi14 >= 35) & (rsi14 <= 50)
    not_broken = df["dist_52w_high"] >= -0.12
    df["pullback_setup"] = (uptrend & rsi_band & not_broken).astype(float)

    _ = n  # silence linter; n kept for readability above
    return df


# Which signals are continuous (rank-IC) vs binary flags (conditional
# mean forward return). Binary flags can't use rank-IC meaningfully.
_BINARY_SIGNALS = {"breakout_60d", "pullback_setup"}


def _build_observation_frame(
    universe: list[_StockSeries], *, obs_step: int, min_lead: int = 273,
) -> pd.DataFrame:
    """Sample every stock on a COMMON monthly calendar grid of real
    dates, so each observation date is a genuine point-in-time cross-
    section (all stocks priced on the same day). Returns a long
    DataFrame: one row per (stock, obs_date) with all signals + fwd
    returns + market-neutral excess fwd returns.

    Alignment fix (vs the earlier bar-index version): keying on
    calendar date prevents mixing 2017-for-stock-A with 2024-for-
    stock-B just because both are "the 273rd bar". Stocks that don't
    trade on a given obs date (listed later / delisted earlier) simply
    don't contribute to that cross-section.
    """
    max_h = max(_HORIZONS)

    # Global trading calendar = union of all stocks' dates, sorted.
    all_dates: set[str] = set()
    for s in universe:
        all_dates.update(s.dates)
    cal = sorted(all_dates)
    if len(cal) < min_lead + max_h + obs_step:
        return pd.DataFrame()
    # Monthly observation dates picked from the global calendar.
    obs_dates = cal[min_lead:len(cal) - max_h:obs_step]
    obs_date_set = set(obs_dates)

    frames: list[pd.DataFrame] = []
    for s in universe:
        n = len(s.closes)
        if n < min_lead + max_h:
            continue
        sig = _compute_signals(s)
        # Map this stock's dates → bar position for O(1) lookup.
        pos_by_date = {d: i for i, d in enumerate(s.dates)}
        c = s.closes.to_numpy()
        rows_idx: list[int] = []
        rows_date: list[str] = []
        for d in obs_dates:
            if d not in obs_date_set:
                continue
            i = pos_by_date.get(d)
            if i is None:
                continue  # stock didn't trade that day
            # Need lookback for 12-1 AND lookahead for longest horizon.
            if i < min_lead or i + max_h >= n:
                continue
            rows_idx.append(i)
            rows_date.append(d)
        if not rows_idx:
            continue
        sub = sig.iloc[rows_idx].copy()
        sub["stock_id"] = s.stock_id
        sub["obs_date"] = rows_date
        for h in _HORIZONS:
            sub[f"fwd_{h}"] = np.array(
                [c[i + h] / c[i] - 1.0 if c[i] > 0 else np.nan for i in rows_idx]
            )
        frames.append(sub)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)

    # ── Market-neutral forward returns ──────────────────────────────
    # Subtract the cross-sectional mean at each REAL obs date so the
    # decile-spread + binary analyses measure signal edge, not market
    # direction. Rank-IC is invariant to this shift (rank correlation
    # ignores per-date location), so it's unaffected.
    for h in _HORIZONS:
        col = f"fwd_{h}"
        out[f"xfwd_{h}"] = out[col] - out.groupby("obs_date")[col].transform("mean")
    return out


def _rank_ic_by_date(
    obs: pd.DataFrame, signal: str, fwd_col: str,
) -> tuple[float, float, float]:
    """Per-observation-date Spearman IC, averaged. Returns
    (mean_ic, std_ic, hit_rate). Each `obs_date` value defines a real
    point-in-time cross-section (all stocks priced that day). Spearman
    = Pearson of ranks; computed via pandas rank + numpy corrcoef."""
    ics: list[float] = []
    for _, grp in obs.groupby("obs_date"):
        x = grp[signal]
        y = grp[fwd_col]
        mask = x.notna() & y.notna()
        if mask.sum() < 20:  # need a reasonable cross-section width
            continue
        xr = x[mask].rank()
        yr = y[mask].rank()
        if xr.nunique() < 2 or yr.nunique() < 2:
            continue
        ic = float(np.corrcoef(xr, yr)[0, 1])
        if np.isfinite(ic):
            ics.append(ic)
    if not ics:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(ics)
    mean_ic = float(arr.mean())
    std_ic = float(arr.std(ddof=1)) if len(arr) > 1 else float("nan")
    # Hit rate: fraction of dates where IC had the same sign as the mean.
    sign = np.sign(mean_ic) if mean_ic != 0 else 1.0
    hit = float((np.sign(arr) == sign).mean())
    return mean_ic, std_ic, hit


def _decile_spread(obs: pd.DataFrame, signal: str, fwd_col: str) -> tuple[float, bool]:
    """Cross-sectional quantile-portfolio spread: bucket stocks into
    deciles WITHIN EACH obs date (so decile membership reflects
    relative rank that day, not regime), average the excess fwd
    return per decile across all dates, return (top-bottom, monotonic).

    Why per-date bucketing matters: pooling raw signal values across
    regimes puts all of 2021's high-momentum names in the top decile —
    which then crashed in 2022 — producing a misleadingly negative
    pooled spread even when the per-date rank relationship (the IC) is
    positive. Per-date deciles are the standard quantile-sort and
    align the spread sign with the IC sign for a genuine signal."""
    sub = obs[["obs_date", signal, fwd_col]].dropna()
    if len(sub) < _N_BUCKETS * 20:
        return float("nan"), False
    sub = sub.copy()

    def _bucket(g: pd.Series) -> pd.Series:
        # Need at least _N_BUCKETS distinct values that day to decile.
        if g.nunique() < _N_BUCKETS:
            return pd.Series([np.nan] * len(g), index=g.index)
        try:
            return pd.qcut(g.rank(method="first"), _N_BUCKETS, labels=False)
        except ValueError:
            return pd.Series([np.nan] * len(g), index=g.index)

    sub["bucket"] = sub.groupby("obs_date")[signal].transform(_bucket)
    sub = sub.dropna(subset=["bucket"])
    if sub.empty:
        return float("nan"), False
    means = sub.groupby("bucket")[fwd_col].mean()
    if len(means) < _N_BUCKETS:
        return float("nan"), False
    spread = float(means.iloc[-1] - means.iloc[0])
    diffs = means.diff().dropna()
    monotonic = bool((diffs > 0).all() or (diffs < 0).all())
    return spread, monotonic


def _conditional_return(obs: pd.DataFrame, flag: str, fwd_col: str) -> tuple[float, float, int]:
    """For a binary flag signal: (mean fwd return when flag=1,
    mean when flag=0, n_flagged). The edge is on=minus-off."""
    sub = obs[[flag, fwd_col]].dropna()
    on = sub[sub[flag] >= 0.5][fwd_col]
    off = sub[sub[flag] < 0.5][fwd_col]
    if len(on) < 50 or len(off) < 50:
        return float("nan"), float("nan"), len(on)
    return float(on.mean()), float(off.mean()), int(len(on))


def run(*, us_only: bool, min_bars: int, obs_step: int) -> None:
    db = SessionLocal()
    try:
        logger.info(
            f"[entry_ic] loading universe (us_only={us_only}, "
            f"min_bars={min_bars}) ..."
        )
        universe = _load_universe(db, us_only=us_only, min_bars=min_bars)
        logger.info(f"[entry_ic] {len(universe)} stocks eligible")
        if not universe:
            print("No eligible stocks — lower --min-bars or drop --us-only.")
            return
        obs = _build_observation_frame(universe, obs_step=obs_step)
        if obs.empty:
            print("No observations produced.")
            return
        n_dates = obs["obs_date"].nunique()
        logger.info(
            f"[entry_ic] {len(obs):,} observations across "
            f"~{n_dates} monthly cross-sections"
        )

        continuous = [
            "mom_12_1", "mom_90d", "mom_30d", "px_vs_ema200", "trend_stack",
            "rsi14", "rsi_below_50", "dist_52w_high", "vol_ratio",
            "bb_contraction",
        ]
        binary = ["breakout_60d", "pullback_setup"]

        print()
        print("=" * 92)
        print(f"  CONTINUOUS SIGNALS — rank-IC (mean) / IR / decile-spread / monotonic / hit")
        print(f"  universe={len(universe)} stocks  obs={len(obs):,}  dates~{n_dates}  "
              f"{'US-only' if us_only else 'ALL'}")
        print("=" * 92)
        header = f"{'signal':<16}" + "".join(f"{'h='+str(h):>22}" for h in _HORIZONS)
        print(header)
        print("-" * 92)
        for sig in continuous:
            cells = []
            for h in _HORIZONS:
                fwd = f"fwd_{h}"
                # IC on raw fwd (rank-invariant to demeaning anyway);
                # decile spread on MARKET-NEUTRAL excess fwd return.
                ic, std, hit = _rank_ic_by_date(obs, sig, fwd)
                spread, mono = _decile_spread(obs, sig, f"xfwd_{h}")
                ir = ic / std if (std and np.isfinite(std) and std > 0) else float("nan")
                mono_mark = "M" if mono else " "
                cells.append(
                    f"IC{ic:+.3f} IR{ir:+.2f} {spread*100:+.1f}%{mono_mark}{hit*100:.0f}"
                )
            print(f"{sig:<16}" + "".join(f"{c:>22}" for c in cells))

        print()
        print("=" * 92)
        print("  BINARY SETUP FLAGS — mean fwd return when ON vs OFF (edge = on-off)")
        print("=" * 92)
        bhdr = f"{'flag':<16}" + "".join(f"{'h='+str(h):>22}" for h in _HORIZONS)
        print(bhdr)
        print("-" * 92)
        for flag in binary:
            cells = []
            for h in _HORIZONS:
                # Market-neutral excess return when flag on vs off — the
                # edge is now "excess vs the universe that day", not
                # contaminated by overall market direction.
                fwd = f"xfwd_{h}"
                on, off, n_on = _conditional_return(obs, flag, fwd)
                edge = (on - off) if (np.isfinite(on) and np.isfinite(off)) else float("nan")
                cells.append(f"on{on*100:+.1f} off{off*100:+.1f} d{edge*100:+.1f}%")
            print(f"{flag:<16}" + "".join(f"{c:>22}" for c in cells))
        print()
        print("Legend: IC=mean rank-IC, IR=IC/std(IC), %=top-bottom decile fwd-return")
        print("        spread, M=monotonic deciles, hit=% dates IC kept its sign.")
        print("        Binary: on/off = mean fwd %, d = edge (on minus off).")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--us-only", action="store_true")
    ap.add_argument("--min-bars", type=int, default=800)
    ap.add_argument("--obs-step", type=int, default=21)
    args = ap.parse_args()
    run(us_only=args.us_only, min_bars=args.min_bars, obs_step=args.obs_step)
