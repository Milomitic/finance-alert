"""Does SECTOR-relative strength carry edge over UNIVERSE-relative? (gates #4)

The Tecnico lens ranks trailing return into a single UNIVERSE-wide percentile
(rel_strength). The roadmap #4 proposal adds a SECTOR-relative percentile, on
the hypothesis that a 75th-pct universe name can be a laggard within a hot
sector. This study validates that BEFORE shipping it: no-look-ahead, from stored
ohlcv_daily only.

For each obs date (stepped), per stock: trailing return over `lookback` bars
(the rel_strength signal) and forward return over `horizon` bars (the outcome).
Per date, rank trailing into a universe percentile AND a within-sector
percentile, then measure the cross-sectional rank-IC of each vs forward return,
plus the PARTIAL IC of the sector rank after regressing out the universe rank
(the incremental edge). Averaged over dates. Ship #4 only if the partial IC is
positive and material.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.rel_strength_ic --sample 600 --step 21
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np
from loguru import logger
from sqlalchemy import select

import app.core.db as dbm
from app.models import Stock
from app.services.signal_outcome_service import _load_universe_closes

_MIN_UNIVERSE = 50   # min stocks on a date to compute a universe IC
_MIN_SECTOR = 8      # min stocks in a sector on a date to compute a sector pct


def _rankpct(x: np.ndarray) -> np.ndarray:
    """Average-rank percentile in [0,1]."""
    order = x.argsort()
    ranks = np.empty(len(x), dtype="float64")
    ranks[order] = np.arange(len(x))
    # average ties
    return (ranks + 1) / len(x)


def _ic(signal: np.ndarray, fwd: np.ndarray) -> float | None:
    """Spearman rank-IC = Pearson corr of the two rankings."""
    if len(signal) < 5:
        return None
    rs, rf = _rankpct(signal), _rankpct(fwd)
    if rs.std() == 0 or rf.std() == 0:
        return None
    return float(np.corrcoef(rs, rf)[0, 1])


def run(*, sample: int, step: int, lookback: int, horizon: int) -> None:
    with dbm.SessionLocal() as db:
        sectors = dict(db.execute(select(Stock.id, Stock.sector)).all())
        closes = _load_universe_closes(db)
    logger.info(f"[rel-strength-ic] {len(closes)} stocks loaded (lookback={lookback} horizon={horizon})")
    if sample and len(closes) > sample:
        closes = dict(list(closes.items())[:sample])

    # date -> list of (stock_id, trailing_ret, fwd_ret)
    by_date: dict[object, list[tuple[int, float, float]]] = defaultdict(list)
    for sid, (dates, cs) in closes.items():
        n = len(cs)
        for i in range(lookback, n - horizon, step):
            c0, cL, cH = cs[i], cs[i - lookback], cs[i + horizon]
            if c0 > 0 and cL > 0:
                by_date[dates[i]].append((sid, c0 / cL - 1.0, cH / c0 - 1.0))

    ic_uni, ic_sec, ic_partial, dec_uni, dec_sec = [], [], [], [], []
    for _d, rows in by_date.items():
        if len(rows) < _MIN_UNIVERSE:
            continue
        sid = np.array([r[0] for r in rows])
        trail = np.array([r[1] for r in rows])
        fwd = np.array([r[2] for r in rows])
        uni = _rankpct(trail)
        u = _ic(uni, fwd)
        if u is not None:
            ic_uni.append(u)
            # decile spread (universe)
            top, bot = fwd[uni >= 0.9], fwd[uni <= 0.1]
            if len(top) and len(bot):
                dec_uni.append(float(top.mean() - bot.mean()))

        # sector percentiles (only sectors with enough names this date)
        sec_pct = np.full(len(rows), np.nan)
        by_sec: dict[str, list[int]] = defaultdict(list)
        for j, s in enumerate(sid):
            sec = sectors.get(int(s))
            if sec:
                by_sec[sec].append(j)
        for js in by_sec.values():
            if len(js) >= _MIN_SECTOR:
                sec_pct[js] = _rankpct(trail[js])
        m = ~np.isnan(sec_pct)
        if m.sum() >= 5:
            s_ic = _ic(sec_pct[m], fwd[m])
            if s_ic is not None:
                ic_sec.append(s_ic)
                top, bot = fwd[m][sec_pct[m] >= 0.9], fwd[m][sec_pct[m] <= 0.1]
                if len(top) and len(bot):
                    dec_sec.append(float(top.mean() - bot.mean()))
            # partial IC: residual of fwd ~ uni_rank, then IC(sector_rank, resid)
            ur, fr = _rankpct(uni[m]), _rankpct(fwd[m])
            if ur.std() > 0:
                beta = np.cov(ur, fr)[0, 1] / ur.var()
                resid = fr - beta * ur
                p = _ic(sec_pct[m], resid)
                if p is not None:
                    ic_partial.append(p)

    def _stat(name, arr):
        if not arr:
            print(f"  {name:<26} (no data)")
            return
        a = np.array(arr)
        print(f"  {name:<26} mean={a.mean():+.4f}  median={np.median(a):+.4f}  "
              f"n_dates={len(a)}  t≈{a.mean()/(a.std(ddof=1)/np.sqrt(len(a))+1e-9):+.2f}")

    print(f"\n{'#'*70}\n#  REL-STRENGTH IC STUDY  (lookback={lookback}d, horizon={horizon}d)")
    print(f"#  universe={len(closes)} stocks, {len(by_date)} obs dates\n{'#'*70}")
    _stat("IC universe-rel", ic_uni)
    _stat("IC sector-rel", ic_sec)
    _stat("IC sector PARTIAL (incr.)", ic_partial)
    print()
    _stat("decile spread universe", dec_uni)
    _stat("decile spread sector", dec_sec)
    print("\nShip #4 (sector-relative) only if IC sector PARTIAL is positive AND "
          "material (t>~2). A flat/negative partial = universe rank already "
          "captures it → keep universe-only, ship the null.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=600)
    ap.add_argument("--step", type=int, default=21)
    ap.add_argument("--lookback", type=int, default=63)
    ap.add_argument("--horizon", type=int, default=21)
    a = ap.parse_args()
    run(sample=a.sample, step=a.step, lookback=a.lookback, horizon=a.horizon)
