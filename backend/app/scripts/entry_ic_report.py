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
from datetime import date

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from app.core.db import SessionLocal
from app.indicators.ema import ema as ema_indicator
from app.indicators.rsi import rsi as rsi_indicator


# Forward-return horizons in trading days: ~1 week, ~1 month, ~1
# quarter, ~1 year. The 252d horizon is the fair test for SLOW factors
# (value / quality / growth) which express over quarters-to-years, not
# weeks — judging fundamentals only at <=63d is biased toward fast
# (momentum) signals.
_HORIZONS = (5, 21, 63, 252)
# Deciles for the spread analysis.
_N_BUCKETS = 10


@dataclass
class _StockSeries:
    stock_id: int
    ticker: str
    closes: pd.Series   # indexed 0..N-1, chronological
    volumes: pd.Series
    dates: list[str]    # ISO date per bar position (same length as closes)
    sector: str         # current sector (static proxy for the XS test)


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
            SELECT s.id, s.ticker, s.sector
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
    sector_by_id = {r[0]: (r[2] or "—") for r in rows}
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
                sector=sector_by_id.get(cur_id, "—"),
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
        sub["sector"] = s.sector
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


def _ramp3_vec(v: np.ndarray, *, full: float, half: float, zero: float) -> np.ndarray:
    """Vectorised mirror of score_service._ramp3 for the retune
    validation. Same two-segment piecewise-linear logic, both
    orientations. NaN in → NaN out."""
    out = np.full_like(v, np.nan, dtype="float64")
    hs = 50.0
    if full > zero:  # higher-is-better
        out = np.where(v >= full, 100.0, out)
        out = np.where(v <= zero, 0.0, out)
        mid_hi = (v < full) & (v >= half)
        out = np.where(mid_hi, hs + (100.0 - hs) * (v - half) / (full - half), out)
        mid_lo = (v > zero) & (v < half)
        out = np.where(mid_lo, hs * (v - zero) / (half - zero), out)
    else:  # lower-is-better (full < zero)
        out = np.where(v <= full, 100.0, out)
        out = np.where(v >= zero, 0.0, out)
        mid_hi = (v > full) & (v <= half)
        out = np.where(mid_hi, hs + (100.0 - hs) * (half - v) / (half - full), out)
        mid_lo = (v < zero) & (v > half)
        out = np.where(mid_lo, hs * (zero - v) / (zero - half), out)
    return out


def _rsi_staircase_vec(rsi: np.ndarray) -> np.ndarray:
    """Vectorised mirror of the RSI staircase in _momentum."""
    out = np.full_like(rsi, np.nan, dtype="float64")
    out = np.where(rsi < 25, 70.0, out)
    out = np.where((rsi >= 25) & (rsi < 30), 80.0, out)
    out = np.where((rsi >= 30) & (rsi < 45), 75.0, out)
    out = np.where((rsi >= 45) & (rsi <= 60), 60.0, out)
    out = np.where((rsi > 60) & (rsi <= 70), 40.0, out)
    out = np.where(rsi > 70, 20.0, out)
    return out


def _weighted_present(scores: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    """Missing-data-neutralised weighted average — mirrors
    score_service._aggregate: per row, sum(score*weight) over the
    components that are present (non-NaN), divided by sum of present
    weights. Rows with no present component → NaN."""
    n = len(next(iter(scores.values())))
    num = np.zeros(n)
    den = np.zeros(n)
    for k, w in weights.items():
        s = scores[k]
        present = ~np.isnan(s)
        num = num + np.where(present, s * w, 0.0)
        den = den + np.where(present, w, 0.0)
    return np.where(den > 0, num / den, np.nan)


def _validate_retune(obs: pd.DataFrame) -> None:
    """Compare the momentum-pillar composite IC under the OLD config
    (pre-retune) vs the NEW config (post-retune), to confirm the
    change is a measured improvement and not a guess.

    Faithful proxy: covers the 7 momentum components the harness
    computes (12-1, trend_stack, px_vs_ema200, rsi, mom_30d, mom_90d,
    dist_52w_high) — including ALL 3 that changed. The 4 omitted
    components (macd / bb / adx / relative_strength) are identical
    across both configs, so the OLD->NEW delta is unaffected by their
    absence (they'd only shift the absolute IC level equally).
    """
    # Ramp the shared components once (identical in both configs).
    score_1211 = _ramp3_vec(obs["mom_12_1"].to_numpy(), full=0.50, half=0.0, zero=-0.30)
    score_px = _ramp3_vec(obs["px_vs_ema200"].to_numpy(), full=0.15, half=0.0, zero=-0.15)
    score_rsi = _rsi_staircase_vec(obs["rsi14"].to_numpy())
    score_trend = obs["trend_stack"].to_numpy() / 3.0 * 100.0  # 0-3 -> 0-100
    score_mom90 = _ramp3_vec(obs["mom_90d"].to_numpy(), full=0.20, half=0.0, zero=-0.15)
    score_dist = _ramp3_vec(obs["dist_52w_high"].to_numpy(), full=-0.02, half=-0.15, zero=-0.40)

    # The two configurations of the changed components.
    mom30 = obs["mom_30d"].to_numpy()
    score_mom30_old = _ramp3_vec(mom30, full=0.10, half=0.0, zero=-0.10)   # higher-better
    score_mom30_new = _ramp3_vec(mom30, full=-0.15, half=0.0, zero=0.15)   # contrarian

    shared = {
        "s_1211": score_1211, "s_px": score_px,
        "s_rsi": score_rsi, "s_trend": score_trend,
    }
    obs = obs.copy()
    obs["mom_OLD"] = _weighted_present(
        {**shared, "s_mom30": score_mom30_old, "s_mom90": score_mom90},
        {"s_1211": 0.22, "s_trend": 0.16, "s_px": 0.10, "s_rsi": 0.08,
         "s_mom30": 0.06, "s_mom90": 0.10},
    )
    obs["mom_NEW"] = _weighted_present(
        {**shared, "s_mom30": score_mom30_new, "s_mom90": score_mom90, "s_dist": score_dist},
        {"s_1211": 0.22, "s_trend": 0.16, "s_px": 0.10, "s_rsi": 0.08,
         "s_mom30": 0.06, "s_mom90": 0.04, "s_dist": 0.06},
    )

    print()
    print("=" * 78)
    print("  RETUNE VALIDATION — momentum pillar composite IC: OLD vs NEW")
    print("  (7-component proxy; the 3 changed components are all included)")
    print("=" * 78)
    print(f"{'config':<10}" + "".join(f"{'h='+str(h):>22}" for h in _HORIZONS))
    print("-" * 78)
    for label, col in (("OLD", "mom_OLD"), ("NEW", "mom_NEW")):
        cells = []
        for h in _HORIZONS:
            ic, std, hit = _rank_ic_by_date(obs, col, f"fwd_{h}")
            ir = ic / std if (std and np.isfinite(std) and std > 0) else float("nan")
            cells.append(f"IC{ic:+.4f} IR{ir:+.2f} hit{hit*100:.0f}")
        print(f"{label:<10}" + "".join(f"{c:>22}" for c in cells))
    # Delta row
    cells = []
    for h in _HORIZONS:
        ic_o, _, _ = _rank_ic_by_date(obs, "mom_OLD", f"fwd_{h}")
        ic_n, _, _ = _rank_ic_by_date(obs, "mom_NEW", f"fwd_{h}")
        cells.append(f"dIC{(ic_n - ic_o):+.4f}")
    print(f"{'NEW-OLD':<10}" + "".join(f"{c:>22}" for c in cells))
    print()
    print("  Positive NEW-OLD dIC = the retune improved the pillar's")
    print("  cross-sectional predictive power. (IC = mean per-date rank-IC")
    print("  of the momentum composite vs forward return.)")
    print()


def _build_mom_new(obs: pd.DataFrame) -> pd.Series:
    """Recompute the post-retune momentum composite (mom_NEW) as a
    Series — shared helper for the XS validation."""
    score_1211 = _ramp3_vec(obs["mom_12_1"].to_numpy(), full=0.50, half=0.0, zero=-0.30)
    score_px = _ramp3_vec(obs["px_vs_ema200"].to_numpy(), full=0.15, half=0.0, zero=-0.15)
    score_rsi = _rsi_staircase_vec(obs["rsi14"].to_numpy())
    score_trend = obs["trend_stack"].to_numpy() / 3.0 * 100.0
    score_mom90 = _ramp3_vec(obs["mom_90d"].to_numpy(), full=0.20, half=0.0, zero=-0.15)
    score_dist = _ramp3_vec(obs["dist_52w_high"].to_numpy(), full=-0.02, half=-0.15, zero=-0.40)
    score_mom30 = _ramp3_vec(obs["mom_30d"].to_numpy(), full=-0.15, half=0.0, zero=0.15)
    comp = _weighted_present(
        {"s_1211": score_1211, "s_px": score_px, "s_rsi": score_rsi,
         "s_trend": score_trend, "s_mom30": score_mom30,
         "s_mom90": score_mom90, "s_dist": score_dist},
        {"s_1211": 0.22, "s_trend": 0.16, "s_px": 0.10, "s_rsi": 0.08,
         "s_mom30": 0.06, "s_mom90": 0.04, "s_dist": 0.06},
    )
    return pd.Series(comp, index=obs.index)


def _validate_xs(obs: pd.DataFrame) -> None:
    """Test the cross-sectional engine's core mechanism on the one
    pillar that is point-in-time safe (momentum): does ranking
    SECTOR-RELATIVE predict forward returns better than ABSOLUTE?

    HONEST SCOPE NOTE printed in the output: the XS engine's biggest
    intended benefit is on the FUNDAMENTAL pillars (value/quality —
    where 'cheap' only means something relative to the sector). Those
    can't be backtested without point-in-time fundamentals, which we
    don't have. So this validates the *mechanism* on momentum only —
    where sector-neutralisation is known to help LEAST (sector
    momentum is itself a real effect). Read the result as a lower
    bound on the engine's value, not the whole story.
    """
    obs = obs.copy()
    obs["mom"] = _build_mom_new(obs)

    # Sector-relative percentile of mom WITHIN each (obs_date, sector).
    def _sector_pct(g: pd.DataFrame) -> pd.Series:
        return g.groupby("sector")["mom"].rank(pct=True) * 100.0

    obs["mom_secrel"] = (
        obs.groupby("obs_date", group_keys=False).apply(_sector_pct)
    )

    print()
    print("=" * 78)
    print("  XS-ENGINE MECHANISM TEST — momentum: ABSOLUTE vs SECTOR-RELATIVE")
    print("=" * 78)
    print(f"{'ranking':<14}" + "".join(f"{'h='+str(h):>20}" for h in _HORIZONS))
    print("-" * 78)
    for label, col in (("absolute", "mom"), ("sector-rel", "mom_secrel")):
        cells = []
        for h in _HORIZONS:
            ic, std, hit = _rank_ic_by_date(obs, col, f"fwd_{h}")
            ir = ic / std if (std and np.isfinite(std) and std > 0) else float("nan")
            cells.append(f"IC{ic:+.4f} IR{ir:+.2f} h{hit*100:.0f}")
        print(f"{label:<14}" + "".join(f"{c:>20}" for c in cells))
    cells = []
    for h in _HORIZONS:
        a, _, _ = _rank_ic_by_date(obs, "mom", f"fwd_{h}")
        s, _, _ = _rank_ic_by_date(obs, "mom_secrel", f"fwd_{h}")
        cells.append(f"dIC{(s - a):+.4f}")
    print(f"{'secrel-abs':<14}" + "".join(f"{c:>20}" for c in cells))
    print()
    print("  CAVEAT: validates the XS MECHANISM on momentum only (point-in-")
    print("  time safe). The engine's main value is on value/quality pillars")
    print("  vs sector — NOT backtestable here without point-in-time")
    print("  fundamentals. Treat as a lower bound, not a verdict.")
    print()


# ── Fundamental pillar validation (phase 2/3) ────────────────────────
# Split-immune fundamental signals only (ratios of TOTAL quantities or
# per-period values that survive splits). Value (P/E, P/B) is excluded:
# it mixes split-adjusted OHLCV price with SEC's unadjusted per-share /
# share-count data, which would corrupt the ratio without split-history
# reconciliation. Deferred to a follow-up.
_FUND_SIGNALS = [
    "net_margin", "gross_margin", "operating_margin", "roe", "roa",
    "fcf_to_ni", "fcf_margin", "debt_to_equity", "rev_yoy", "ni_yoy",
]


def _load_pit_fundamentals(db, universe: list[_StockSeries]) -> dict[int, dict]:
    """Bulk-fetch + cache the SEC PIT fact history for every stock in
    the universe. First run hits SEC (rate-limited ~6/s inside the
    service); subsequent runs are L2 cache hits. Returns
    {stock_id: fact_history}. Stocks that don't resolve to a CIK
    (non-US / ADRs) get an empty history and are skipped downstream."""
    from app.services import sec_fundamentals_history as sf
    out: dict[int, dict] = {}
    n = len(universe)
    resolved = 0
    for i, s in enumerate(universe):
        try:
            hist = sf.get_fact_history(db, s.ticker)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[fund] {s.ticker} history failed: {e}")
            hist = {}
        out[s.stock_id] = hist
        if hist:
            resolved += 1
        if (i + 1) % 50 == 0 or i + 1 == n:
            logger.info(f"[fund] PIT history {i + 1}/{n} (resolved {resolved})")
    return out


def _fund_signals_as_of(hist: dict, as_of: date) -> dict[str, float | None]:
    """Compute the split-immune fundamental signals as of `as_of`,
    using only facts FILED by then (PIT). Division guards return None
    on zero/None denominators rather than inf/NaN."""
    from app.services import sec_fundamentals_history as sf
    import datetime as _dt

    def _ttm(c):
        return sf.ttm_flow(hist, c, as_of)

    def _inst(c):
        fp = sf.latest_instant(hist, c, as_of)
        return fp.val if fp else None

    rev = _ttm("revenue")
    ni = _ttm("net_income")
    gp = _ttm("gross_profit")
    oi = _ttm("operating_income")
    ocf = _ttm("operating_cash_flow")
    capex = _ttm("capex")
    eq = _inst("equity")
    assets = _inst("assets")
    debt = _inst("long_term_debt")

    def _safe_div(a, b):
        if a is None or b is None or b == 0:
            return None
        return a / b

    fcf = (ocf - capex) if (ocf is not None and capex is not None) else None
    # capex in companyfacts is a positive outflow magnitude; FCF = OCF - capex.

    out: dict[str, float | None] = {
        "net_margin": _safe_div(ni, rev),
        "gross_margin": _safe_div(gp, rev),
        "operating_margin": _safe_div(oi, rev),
        "roe": _safe_div(ni, eq),
        "roa": _safe_div(ni, assets),
        "fcf_to_ni": _safe_div(fcf, ni),
        "fcf_margin": _safe_div(fcf, rev),
        # debt_to_equity expected NEGATIVE IC (more leverage = riskier);
        # we keep raw and read the sign.
        "debt_to_equity": _safe_div(debt, eq),
    }
    # YoY growth: compare TTM now vs TTM one year ago (both PIT-filtered).
    prev = as_of - _dt.timedelta(days=365)
    rev_prev = sf.ttm_flow(hist, "revenue", prev)
    ni_prev = sf.ttm_flow(hist, "net_income", prev)
    out["rev_yoy"] = (
        (rev / rev_prev - 1.0) if (rev and rev_prev and rev_prev > 0) else None
    )
    # NI YoY only meaningful when prior NI is positive (avoid sign flips).
    out["ni_yoy"] = (
        (ni / ni_prev - 1.0) if (ni is not None and ni_prev and ni_prev > 0) else None
    )
    return out


def _build_fundamental_obs(
    universe: list[_StockSeries], histories: dict[int, dict], *, obs_step: int,
    min_lead: int = 273,
) -> pd.DataFrame:
    """Calendar-aligned observation frame of FUNDAMENTAL signals +
    forward returns + sector. Same monthly grid / market-neutral
    excess-return treatment as the technical frame."""
    max_h = max(_HORIZONS)
    all_dates: set[str] = set()
    for s in universe:
        all_dates.update(s.dates)
    cal = sorted(all_dates)
    if len(cal) < min_lead + max_h + obs_step:
        return pd.DataFrame()
    obs_dates = cal[min_lead:len(cal) - max_h:obs_step]

    rows: list[dict] = []
    for s in universe:
        hist = histories.get(s.stock_id) or {}
        if not hist:
            continue
        pos_by_date = {d: i for i, d in enumerate(s.dates)}
        c = s.closes.to_numpy()
        n = len(c)
        for d in obs_dates:
            i = pos_by_date.get(d)
            if i is None or i < min_lead or i + max_h >= n:
                continue
            sig = _fund_signals_as_of(hist, date.fromisoformat(d))
            if all(v is None for v in sig.values()):
                continue
            row = {"stock_id": s.stock_id, "obs_date": d, "sector": s.sector}
            row.update(sig)
            for h in _HORIZONS:
                row[f"fwd_{h}"] = c[i + h] / c[i] - 1.0 if c[i] > 0 else np.nan
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    for h in _HORIZONS:
        col = f"fwd_{h}"
        out[f"xfwd_{h}"] = out[col] - out.groupby("obs_date")[col].transform("mean")
    return out


def _validate_fundamentals(obs: pd.DataFrame) -> None:
    """IC report for the split-immune fundamental signals, PLUS the
    absolute-vs-sector-relative comparison that answers the open
    SCORE_ENGINE_XS question for the quality pillars: does sector-
    neutralising these signals improve their cross-sectional IC?"""
    print()
    print("=" * 94)
    print("  FUNDAMENTAL SIGNALS (PIT, split-immune) — rank-IC absolute vs sector-relative")
    print(f"  obs={len(obs):,}  dates~{obs['obs_date'].nunique()}  "
          f"stocks~{obs['stock_id'].nunique()}")
    print("=" * 94)
    print(f"{'signal':<16}{'rank':<10}" + "".join(f"{'h='+str(h):>16}" for h in _HORIZONS))
    print("-" * 94)
    for sig in _FUND_SIGNALS:
        if sig not in obs.columns:
            continue
        # Absolute IC
        abs_cells = []
        for h in _HORIZONS:
            ic, std, hit = _rank_ic_by_date(obs, sig, f"fwd_{h}")
            ir = ic / std if (std and np.isfinite(std) and std > 0) else float("nan")
            abs_cells.append(f"IC{ic:+.3f} IR{ir:+.2f}")
        print(f"{sig:<16}{'absolute':<10}" + "".join(f"{c:>16}" for c in abs_cells))
        # Sector-relative IC
        obs2 = obs.copy()
        obs2[sig + "_sr"] = (
            obs2.groupby("obs_date", group_keys=False)
            .apply(lambda g: g.groupby("sector")[sig].rank(pct=True) * 100.0)
        )
        sr_cells = []
        for h in _HORIZONS:
            ic, std, hit = _rank_ic_by_date(obs2, sig + "_sr", f"fwd_{h}")
            sr_cells.append(f"IC{ic:+.3f}")
        print(f"{'':<16}{'sector-rel':<10}" + "".join(f"{c:>16}" for c in sr_cells))
    print()
    print("  Compare 'absolute' vs 'sector-rel' IC per signal: if sector-rel")
    print("  is consistently higher, the XS engine helps that pillar (supports")
    print("  turning SCORE_ENGINE_XS on, at least selectively for fundamentals).")
    print()


def run(*, us_only: bool, min_bars: int, obs_step: int,
        validate_retune: bool = False, validate_xs: bool = False,
        validate_fundamentals: bool = False) -> None:
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

        # Retune validation short-circuits the full signal report —
        # it just needs the observation frame.
        if validate_retune:
            _validate_retune(obs)
            return
        if validate_xs:
            _validate_xs(obs)
            return
        if validate_fundamentals:
            logger.info("[fund] loading PIT fundamentals (first run hits SEC)...")
            histories = _load_pit_fundamentals(db, universe)
            fobs = _build_fundamental_obs(universe, histories, obs_step=obs_step)
            if fobs.empty:
                print("No fundamental observations produced.")
                return
            _validate_fundamentals(fobs)
            return

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
    ap.add_argument("--validate-retune", action="store_true",
                    help="Compare momentum-pillar IC OLD vs NEW config")
    ap.add_argument("--validate-xs", action="store_true",
                    help="Compare momentum IC absolute vs sector-relative")
    ap.add_argument("--validate-fundamentals", action="store_true",
                    help="IC of PIT fundamental signals (SEC) abs vs sector-rel")
    args = ap.parse_args()
    run(us_only=args.us_only, min_bars=args.min_bars, obs_step=args.obs_step,
        validate_retune=args.validate_retune, validate_xs=args.validate_xs,
        validate_fundamentals=args.validate_fundamentals)
