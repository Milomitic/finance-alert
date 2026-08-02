"""ONE replay, MANY stamps: the substrate for the conditional screen.

The question behind this: does a detector's skill depend on the STATE the
market was in when it fired? Five previous studies asked narrower versions of
that and all came back null, so this one widens the search instead of
deepening it — many candidate conditions tested together, with the statistics
that make "many" honest (see `conditional_screen_grid`, which does that half).

The split of labour matters. The replay is the expensive part (hours); the
analysis is seconds. So this script does NOT aggregate: it writes ONE ROW PER
SIGNAL with every condition stamped, and the grid script re-reads that file as
often as we want — new hypotheses, new bucketings, new corrections, all
without paying for the replay again. The earlier regime study aggregated
inline and had to be re-run four times.

WHAT IS STAMPED, and why each one is allowed to be here.

The bar every condition must clear is ORTHOGONALITY: it must carry information
that is not already a transform of the stock's own price series. Ten more
indicators derived from the same closes would just re-test what the
confirmation-count study already answered (flat).

  macro (FRED daily state series, `backfill_macro_history`):
    vix_level    — implied vol regime
    vix_chg5     — 5-day change in the VIX (stress rising vs subsiding)
    curve        — 10y-2y spread (T10Y2Y)
    credit       — Baa-over-10y spread (BAA10Y)
  cross-section (from the universe, aggregate rather than single-name):
    breadth      — share of the universe above its own EMA200 that day
    sector_rs    — the stock's 63d return minus its SECTOR's median 63d return
  stock state (price-derived, but a state rather than a signal):
    atr_regime   — the name's own ATR%, ranked against its own trailing year
  control:
    regime       — close vs EMA200. NOT a hypothesis: a NEGATIVE CONTROL.

The negative control is the part worth reading twice. The 2026-06-10 study
established that under a tone-symmetric benchmark there is no credible regime
effect for any detector. So the pipeline has a cell whose answer is already
known to be null. If the grid ever reports `regime` as a survivor, the finding
is not a finding — the pipeline is broken, and every other cell in that run is
suspect too.

THREE LOOK-AHEAD TRAPS, all live, all handled here.

1. Tercile boundaries. Cutting a 10-year series into "low/mid/high" using the
   WHOLE series embeds the future in the label: in 2016 nobody knew what the
   2020 vol distribution would be. Every macro/breadth boundary is therefore
   an EXPANDING-WINDOW quantile — computed from observations strictly before
   the fire date, after a burn-in. Cross-sectional conditions (sector_rs) need
   no such treatment: a rank among peers on day t uses only day t.
2. Publication lag. FRED revises, and some series post late in the day. Every
   macro read is taken from the last observation dated STRICTLY BEFORE the
   fire date, never same-day. Costs a little signal, removes the whole
   question.
3. The benchmark itself. The hit is measured against the universe MEDIAN, not
   the mean. This is the lesson of the trend_pullback artifact: cross-sectional
   returns are right-skewed, so P(beat mean) < 50% under zero skill, which
   manufactures a split for any detector whose tone correlates with the
   condition. The median is 50/50 under zero skill by construction.

Clustering is NOT corrected here — it is recorded. Each row carries its bar
index so the grid can collapse overlapping forward windows of the same name
into episodes and size the confidence intervals on those instead of on the
nominal count, which grossly overstates the independent sample.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.conditional_screen_replay --sample 300 --step 3

Output: app/data/conditional_screen_rows.csv.gz (read by conditional_screen_grid).
"""
from __future__ import annotations

import argparse
import csv
import gzip
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
from loguru import logger

from app.scripts.signal_detector_outcomes import _detector_horizon
from app.scripts.signal_factor_outcomes import H_LONG, H_MED, H_SHORT, _load_universe
from app.signals.runner import detect_signals

_OUT_DEFAULT = "app/data/conditional_screen_rows.csv.gz"

# Expanding-window quantiles need enough history to mean anything. Below this
# many prior observations a condition is stamped "na" rather than guessed.
_BURN_IN = 250
# Trailing window for the stock's own ATR ranking (~1 trading year).
_ATR_WINDOW = 252
# Lookback for the relative-strength comparison against the sector.
_RS_LOOKBACK = 63

_TERCILE_LABELS = ("low", "mid", "high")


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    """Causal EMA — value at i uses only values[:i+1]."""
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    acc = float(values[0])
    for i, v in enumerate(values):
        acc = alpha * float(v) + (1 - alpha) * acc
        out[i] = acc
    return out


def _load_macro(db) -> dict[str, list[tuple[date, float]]]:
    """{fred_series_id: [(date, value)] sorted ascending}, missing values dropped."""
    from sqlalchemy import text

    rows = db.execute(text(
        """
        SELECT ms.fred_series_id, mo.date, mo.value
        FROM macro_series ms JOIN macro_observations mo ON mo.series_id = ms.id
        WHERE ms.fred_series_id IN ('VIXCLS', 'T10Y2Y', 'BAA10Y')
          AND mo.value IS NOT NULL
        ORDER BY ms.fred_series_id, mo.date
        """
    )).all()
    out: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for sid, d, v in rows:
        if isinstance(d, str):
            d = date.fromisoformat(d)
        out[sid].append((d, float(v)))
    return dict(out)


class _ExpandingTercile:
    """Labels a value by terciles of everything seen STRICTLY EARLIER.

    Feed it a date-ordered series once; ask for a label at any date. The
    boundaries at date d come from observations before d, so a label never
    depends on the future. Returns "na" until `_BURN_IN` observations exist.
    """

    def __init__(self, series: list[tuple[date, float]]) -> None:
        self._dates = [d for d, _ in series]
        self._vals = np.array([v for _, v in series], dtype=float)

    def _idx_before(self, d: date) -> int:
        """Count of observations strictly before `d` (they are sorted)."""
        lo, hi = 0, len(self._dates)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._dates[mid] < d:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def label_at(self, d: date) -> str:
        """Tercile of the most recent observation before `d`, cut against the
        distribution of everything before `d`."""
        i = self._idx_before(d)
        if i < _BURN_IN:
            return "na"
        hist = self._vals[:i]
        latest = float(hist[-1])
        q33, q67 = np.percentile(hist, [33.333, 66.667])
        if latest <= q33:
            return _TERCILE_LABELS[0]
        return _TERCILE_LABELS[2] if latest > q67 else _TERCILE_LABELS[1]

    def change_label_at(self, d: date, lookback: int = 5) -> str:
        """Same, for the CHANGE over the last `lookback` observations."""
        i = self._idx_before(d)
        if i < _BURN_IN + lookback:
            return "na"
        hist = self._vals[:i]
        diffs = hist[lookback:] - hist[:-lookback]
        latest = float(diffs[-1])
        q33, q67 = np.percentile(diffs, [33.333, 66.667])
        if latest <= q33:
            return "down"
        return "up" if latest > q67 else "flat"


def _universe_fwd_medians(universe, horizons) -> dict[int, dict[str, float]]:
    """{h: {date: MEDIAN forward return across the universe}}.

    Tone-symmetric by construction: under zero skill a bull signal beats the
    median exactly as often as a bear signal lags it. The mean is not — see
    the module docstring."""
    out: dict[int, dict[str, float]] = {}
    for h in sorted(set(horizons)):
        by_date: dict[str, list[float]] = defaultdict(list)
        for s in universe:
            c = s.closes
            if len(c) <= h:
                continue
            c0, cH = c[:-h], c[h:]
            ok = c0 > 0
            rets = cH[ok] / c0[ok] - 1.0
            for d, r in zip(np.asarray(s.dates, dtype=object)[:-h][ok], rets, strict=False):
                by_date[d].append(float(r))
        out[h] = {d: float(np.median(v)) for d, v in by_date.items() if len(v) >= 10}
    return out


def _breadth_by_date(universe) -> list[tuple[date, float]]:
    """Share of the universe trading above its own EMA200, per calendar date.

    Cross-sectional and causal: each stock's EMA200 at date d uses only its own
    closes up to d."""
    hits: dict[str, int] = defaultdict(int)
    tot: dict[str, int] = defaultdict(int)
    for s in universe:
        c = s.closes
        if len(c) < 200:
            continue
        e = _ema(c, 200)
        above = c > e
        for d, a in zip(s.dates, above, strict=False):
            tot[d] += 1
            if a:
                hits[d] += 1
    out = [
        (date.fromisoformat(d), hits[d] / tot[d])
        for d in sorted(tot) if tot[d] >= 20
    ]
    return out


def _sector_rs(universe, sectors: dict[int, str]) -> dict[int, dict[str, float]]:
    """{stock_idx: {date: own 63d return - sector MEDIAN 63d return}}.

    Cross-sectional at each date, so inherently point-in-time — no expanding
    window needed. Stocks with no sector are skipped (stamped "na" later)."""
    per_stock: dict[int, dict[str, float]] = {}
    by_sector_date: dict[tuple[str, str], list[float]] = defaultdict(list)
    for sidx, s in enumerate(universe):
        sec = sectors.get(s.stock_id)
        if not sec:
            continue
        c = s.closes
        if len(c) <= _RS_LOOKBACK:
            continue
        base = c[:-_RS_LOOKBACK]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(base > 0, c[_RS_LOOKBACK:] / base - 1.0, np.nan)
        d_slice = s.dates[_RS_LOOKBACK:]
        per_stock[sidx] = dict(zip(d_slice, (float(x) for x in r), strict=False))
        for d, x in zip(d_slice, r, strict=False):
            if np.isfinite(x):
                by_sector_date[(sec, d)].append(float(x))
    med = {k: float(np.median(v)) for k, v in by_sector_date.items() if len(v) >= 5}
    out: dict[int, dict[str, float]] = {}
    for sidx, series in per_stock.items():
        sec = sectors.get(universe[sidx].stock_id)
        rel: dict[str, float] = {}
        for d, x in series.items():
            m = med.get((sec, d))
            if m is not None and np.isfinite(x):
                rel[d] = x - m
        out[sidx] = rel
    return out


def _atr_pct(s) -> np.ndarray:
    """True-range percentage of close, smoothed over 14 bars. Causal."""
    df = s.df
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    prev = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    # Simple causal rolling mean; cumsum keeps it O(n).
    k = 14
    csum = np.concatenate(([0.0], np.cumsum(tr)))
    atr = np.full(len(tr), np.nan)
    if len(tr) > k:
        atr[k:] = (csum[k + 1:] - csum[1:-k]) / k
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(close > 0, atr / close, np.nan)


def _tercile_of_trailing(values: np.ndarray, i: int, window: int) -> str:
    """Rank values[i] against the name's OWN preceding `window` bars."""
    lo = max(0, i - window)
    hist = values[lo:i]
    hist = hist[np.isfinite(hist)]
    if len(hist) < 60 or not np.isfinite(values[i]):
        return "na"
    q33, q67 = np.percentile(hist, [33.333, 66.667])
    v = float(values[i])
    if v <= q33:
        return _TERCILE_LABELS[0]
    return _TERCILE_LABELS[2] if v > q67 else _TERCILE_LABELS[1]


def _static_tercile(value: float, cuts: tuple[float, float]) -> str:
    if not np.isfinite(value):
        return "na"
    if value <= cuts[0]:
        return _TERCILE_LABELS[0]
    return _TERCILE_LABELS[2] if value > cuts[1] else _TERCILE_LABELS[1]


CONDITION_COLUMNS = (
    "vix_level", "vix_chg5", "curve", "credit",
    "breadth", "sector_rs", "atr_regime", "regime",
)


def run(*, sample: int, step: int, window: int, min_bars: int,
        holdout_frac: float, out: str = _OUT_DEFAULT) -> None:
    from sqlalchemy import text

    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
        if not universe:
            print("No eligible stocks.")
            return
        logger.info(f"[screen] {len(universe)} stocks")

        sectors = {
            r[0]: r[1] for r in db.execute(text(
                "SELECT id, sector FROM stocks WHERE sector IS NOT NULL"
            )).all()
        }
        macro = _load_macro(db)
        missing = [s for s in ("VIXCLS", "T10Y2Y", "BAA10Y") if s not in macro]
        if missing:
            logger.warning(
                f"[screen] macro series missing: {missing} — run "
                "app.scripts.backfill_macro_history first; those columns will be 'na'"
            )
        vix = _ExpandingTercile(macro["VIXCLS"]) if "VIXCLS" in macro else None
        curve = _ExpandingTercile(macro["T10Y2Y"]) if "T10Y2Y" in macro else None
        credit = _ExpandingTercile(macro["BAA10Y"]) if "BAA10Y" in macro else None
        logger.info("[screen] macro terciles ready (expanding window)")

        breadth = _ExpandingTercile(_breadth_by_date(universe))
        logger.info("[screen] breadth series ready")

        rs = _sector_rs(universe, sectors)
        # Sector-relative strength is cross-sectional, so its cut points come
        # from the pooled distribution of the SAME quantity — a rank among
        # peers, not a comparison with the future.
        rs_all = np.array(
            [v for per in rs.values() for v in per.values() if np.isfinite(v)],
            dtype=float,
        )
        rs_cuts = (
            (float(np.percentile(rs_all, 33.333)), float(np.percentile(rs_all, 66.667)))
            if len(rs_all) > 1000 else (float("nan"), float("nan"))
        )
        logger.info(f"[screen] sector RS ready ({len(rs_all):,} obs)")

        umed = _universe_fwd_medians(universe, [H_SHORT, H_MED, H_LONG])
        logger.info("[screen] universe forward medians ready")

        all_dates = sorted({d for s in universe for d in s.dates})
        cutoff = all_dates[int(len(all_dates) * (1 - holdout_frac))]
        logger.info(f"[screen] OOS cutoff = {cutoff} (holdout = newest {holdout_frac:.0%})")

        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        n_rows = 0
        with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow((
                "detector", "tone", "date", "stock_id", "bar_i",
                "horizon", "hit", "excess", "period", *CONDITION_COLUMNS,
            ))
            for sidx, s in enumerate(universe):
                df = s.df
                c = s.closes
                n = len(c)
                ema200 = _ema(c, 200)
                atr = _atr_pct(s)
                rs_series = rs.get(sidx, {})
                for i in range(window, n - H_SHORT, step):
                    win = df.iloc[i - window:i + 1].reset_index(drop=True)
                    try:
                        matches = detect_signals(win)
                    except Exception:  # noqa: BLE001 — one bad window must not kill the run
                        continue
                    if not matches:
                        continue
                    d_str = s.dates[i]
                    d_obj = date.fromisoformat(d_str)
                    # Strictly-before reads: no same-day macro, ever.
                    conds = {
                        "vix_level": vix.label_at(d_obj) if vix else "na",
                        "vix_chg5": vix.change_label_at(d_obj) if vix else "na",
                        "curve": curve.label_at(d_obj) if curve else "na",
                        "credit": credit.label_at(d_obj) if credit else "na",
                        "breadth": breadth.label_at(d_obj),
                        "sector_rs": _static_tercile(rs_series.get(d_str, float("nan")), rs_cuts),
                        "atr_regime": _tercile_of_trailing(atr, i, _ATR_WINDOW),
                        "regime": "bull" if c[i] > ema200[i] else "bear",
                    }
                    period = "holdout" if d_str >= cutoff else "train"
                    for m in matches:
                        h = _detector_horizon(m.name)
                        if i + h >= n or c[i] <= 0:
                            continue
                        bench = umed.get(h, {}).get(d_str)
                        if bench is None or not np.isfinite(bench):
                            continue
                        fwd = c[i + h] / c[i] - 1.0
                        excess = (fwd - bench) if m.tone == "bull" else -(fwd - bench)
                        w.writerow((
                            m.name, m.tone, d_str, s.stock_id, i, h,
                            1 if excess > 0 else 0, f"{excess:.6f}", period,
                            *(conds[k] for k in CONDITION_COLUMNS),
                        ))
                        n_rows += 1
                if (sidx + 1) % 25 == 0:
                    logger.info(f"[screen] {sidx + 1}/{len(universe)} stocks, {n_rows:,} rows")

        print(f"\nWrote {n_rows:,} signal rows to {path}")
        print(f"OOS cutoff: {cutoff}")
        print("Next: PYTHONPATH=. python -m app.scripts.conditional_screen_grid")
    finally:
        db.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sample", type=int, default=300,
                   help="max stocks (default 300; None-like 0 = all)")
    p.add_argument("--step", type=int, default=3,
                   help="bars between observation points (default 3)")
    p.add_argument("--window", type=int, default=260,
                   help="bars of history handed to detect_signals (default 260)")
    p.add_argument("--min-bars", type=int, default=400)
    p.add_argument("--holdout-frac", type=float, default=0.3,
                   help="newest share of dates reserved as OOS holdout")
    p.add_argument("--out", default=_OUT_DEFAULT)
    a = p.parse_args()
    run(sample=a.sample or None, step=a.step, window=a.window,
        min_bars=a.min_bars, holdout_frac=a.holdout_frac, out=a.out)
