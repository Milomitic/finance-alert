"""One-off READ-ONLY diagnostic: cross-sectional concentration attack on the
trend_pullback regime finding (50-stock run, step 10). Replays ONLY
trend_pullback with the exact production inputs (extract_ema_cross +
build_context + TrendPullback.detect) and records per-stock identity so we can
test whether a handful of stocks fabricate the bull/bear split.

Outputs:
  1. replication check vs reported numbers (bull 45.9 n=3059 / bear 55.37 n=1340)
  2. per-stock share of bear & bull cells (top contributors)
  3. leave-one-stock-out delta range
  4. stock-level cluster bootstrap CI on delta (resample stocks, 4000 reps)
  5. per-year distribution of bear-cell signals (temporal clustering)
  6. episode count (runs of consecutive fires) -> effective N estimate
"""
from __future__ import annotations

import numpy as np
from collections import defaultdict

from app.scripts.signal_factor_outcomes import _load_universe, _universe_mean_fwd
from app.scripts.signal_detector_outcomes import _detector_horizon
from app.signals.events import extract_ema_cross
from app.signals.context import build_context
from app.signals.detectors.trend_pullback import TrendPullback
from app.scripts.regime_conditioned_outcomes import _ema
from app.core.db import SessionLocal

SAMPLE, STEP, WINDOW, MIN_BARS, HOLDOUT = 50, 10, 500, 400, 0.30
H = _detector_horizon("trend_pullback")
print(f"horizon for trend_pullback = {H} trading days; step={STEP} -> overlap ratio ~{(H-STEP)/H:.0%}")

db = SessionLocal()
universe = _load_universe(db, min_bars=MIN_BARS, sample=SAMPLE)
db.close()
print(f"universe = {len(universe)} stocks: {[s.ticker for s in universe]}")
umean = _universe_mean_fwd(universe)
date_to_idx = umean["_date_to_idx"]

all_dates = sorted({d for s in universe for d in s.dates})
cutoff = all_dates[int(len(all_dates) * (1 - HOLDOUT))]

det = TrendPullback()
# rec: (ticker, regime, period, year, hit, tone, bar_index)
recs = []
for s in universe:
    df = s.df
    c = s.closes
    n = len(c)
    ema200 = _ema(c, 200)
    for i in range(WINDOW, n - 5, STEP):  # mirror study loop bound (n - H_SHORT)
        win = df.iloc[i - WINDOW:i + 1].reset_index(drop=True)
        try:
            events = extract_ema_cross(win, fast=50, slow=200)
            ctx = build_context(win)
            m = det.detect(events, win, ctx)
        except Exception:
            continue
        if m is None:
            continue
        if i + H >= n or c[i] <= 0:
            continue
        di = date_to_idx.get(s.dates[i])
        mean = umean[H][di] if di is not None else np.nan
        if not np.isfinite(mean):
            continue
        regime = "bull" if c[i] > ema200[i] else "bear"
        period = "holdout" if s.dates[i] >= cutoff else "train"
        fwd = c[i + H] / c[i] - 1.0
        dir_excess = (fwd - mean) if m.tone == "bull" else -(fwd - mean)
        recs.append((s.ticker, regime, period, s.dates[i][:4], 1 if dir_excess > 0 else 0, m.tone, i))

print(f"\ntotal trend_pullback obs: {len(recs)}")

def cell(reg):
    return [r for r in recs if r[1] == reg]

bull, bear = cell("bull"), cell("bear")
pB = 100 * np.mean([r[4] for r in bull]) if bull else float("nan")
pb = 100 * np.mean([r[4] for r in bear]) if bear else float("nan")
print(f"REPLICATION: bull {pB:.2f}% (n={len(bull)})  bear {pb:.2f}% (n={len(bear)})  delta {pB-pb:+.2f}pp")
print("  (reported: bull 45.90 n=3059 / bear 55.37 n=1340 / delta -9.48)")

# tone x regime cross-tab
tab = defaultdict(int)
for r in recs:
    tab[(r[1], r[5])] += 1
print(f"\ntone x regime: {dict(tab)}")

# 2. per-stock concentration
for reg, arr in (("bear", bear), ("bull", bull)):
    by_stock = defaultdict(list)
    for r in arr:
        by_stock[r[0]].append(r[4])
    tot = len(arr)
    shares = sorted(((len(v), k, 100*np.mean(v)) for k, v in by_stock.items()), reverse=True)
    top = shares[:10]
    cum = sum(x[0] for x in shares[:5]) / tot * 100
    cum10 = sum(x[0] for x in shares[:10]) / tot * 100
    print(f"\n[{reg}] n={tot}, contributing stocks={len(by_stock)}, top5 share={cum:.1f}%, top10 share={cum10:.1f}%")
    for cnt, tk, hit in top:
        print(f"   {tk:<8} n={cnt:>4} ({100*cnt/tot:4.1f}%)  hit={hit:.1f}%")

# 3. leave-one-stock-out delta
tickers = sorted({r[0] for r in recs})
deltas = {}
for tk in tickers:
    b = [r[4] for r in bull if r[0] != tk]
    e = [r[4] for r in bear if r[0] != tk]
    if b and e:
        deltas[tk] = 100*np.mean(b) - 100*np.mean(e)
vals = sorted(deltas.items(), key=lambda kv: kv[1])
print(f"\nLOSO delta range: [{vals[0][1]:+.2f} (drop {vals[0][0]}), {vals[-1][1]:+.2f} (drop {vals[-1][0]})]")
print(f"  any LOSO delta crosses 0? {any(v >= 0 for _, v in deltas.items())}")

# 4. stock-level cluster bootstrap on delta
rng = np.random.default_rng(42)
per_stock = {tk: ([r[4] for r in bull if r[0] == tk], [r[4] for r in bear if r[0] == tk]) for tk in tickers}
boot = []
for _ in range(4000):
    pick = rng.choice(tickers, size=len(tickers), replace=True)
    bb, ee = [], []
    for tk in pick:
        bb.extend(per_stock[tk][0]); ee.extend(per_stock[tk][1])
    if bb and ee:
        boot.append(100*np.mean(bb) - 100*np.mean(ee))
boot = np.array(boot)
lo, hi = np.percentile(boot, [2.5, 97.5])
print(f"\nstock-cluster bootstrap delta 95% CI: [{lo:+.2f}, {hi:+.2f}]  (point {pB-pb:+.2f})")
print(f"  share of bootstrap deltas >= 0: {np.mean(boot >= 0)*100:.2f}%")

# 5. temporal clustering of bear cell
by_year = defaultdict(list)
for r in bear:
    by_year[r[3]].append(r[4])
print("\nbear-cell by year:")
for y in sorted(by_year):
    arr = by_year[y]
    print(f"   {y}: n={len(arr):>4} ({100*len(arr)/len(bear):4.1f}%)  hit={100*np.mean(arr):.1f}%")

# 6. episodes: consecutive fires (same stock, same regime, gap == STEP bars)
def episodes(arr):
    by_stock = defaultdict(list)
    for r in arr:
        by_stock[r[0]].append(r[6])
    n_ep = 0
    for tk, idxs in by_stock.items():
        idxs.sort()
        n_ep += 1 + sum(1 for a, b in zip(idxs, idxs[1:]) if b - a > STEP)
    return n_ep

epB, epb = episodes(bull), episodes(bear)
print(f"\nepisodes (maximal runs of consecutive fires): bull {epB} (n={len(bull)}), bear {epb} (n={len(bear)})")
# effective N if outcomes within an episode are ~1 obs (63d horizon, 10d step):
print(f"  naive effective-N: bull ~{epB}, bear ~{epb}  -> Wilson half-widths at these N:")
for nm, p, ne in (("bull", pB/100, epB), ("bear", pb/100, epb)):
    hw = 1.96*np.sqrt(p*(1-p)/ne)*100
    print(f"   {nm}: +/-{hw:.2f}pp")
