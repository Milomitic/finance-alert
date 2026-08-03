"""Short-horizon re-scoring of the conditional screen — the flow-impact test.

The full screen tested the detectors at their own horizons (5 / 21 / 63 bars)
against the universe MEDIAN, and found nothing. Two objections to that survive
it, and both are fair:

1. HORIZON. If signals coincide with what triggers other people's algorithms,
   the payoff is order-flow impact, and that lives at ONE TO THREE DAYS. A
   two-day impulse inside a 63-bar window is noise. The screen never looked
   below 5 bars, so this region is genuinely unexplored rather than tested.

2. THE METRIC HIDES BETA ON PURPOSE. A market-neutral hit is measured against
   the universe median, so "everything went up" cancels out by construction.
   If the claim is "we are right because the market rises", the screen could
   not have seen it — it subtracted exactly that. Which is correct for
   measuring SKILL, and useless for answering the question as asked.

So this script re-scores the SAME signals at h = 1, 2, 3, 5 and reports the
absolute and market-neutral hit rates side by side. The gap between the two
columns IS the beta, made visible instead of left ambiguous: whatever the
absolute column shows above 50% that the neutral column does not, you would
have got by being long, without any detector.

It also adds CONCURRENCE as a condition — how many distinct detectors fire on
the same name on the same day. That is the literal form of "several events
coinciding", and unlike the macro conditions it varies across stocks on a
given date, so it is tested on stock-episodes with a genuinely large sample
rather than on a handful of time blocks.

No replay. The rows artifact kept `stock_id` and `bar_i`, so the outcomes are
recomputed by rejoining to stored OHLCV — minutes rather than hours. That
reuse is the whole reason the replay writes raw rows instead of aggregates.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.conditional_screen_shorthz
"""
from __future__ import annotations

import argparse
import csv
import gzip
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from loguru import logger

from app.scripts.conditional_screen_replay import CONDITION_COLUMNS
from app.scripts.signal_factor_outcomes import _load_universe

_IN_DEFAULT = "app/data/conditional_screen_rows.csv.gz"
_OUT_TMPL = "app/data/conditional_screen_h{h}.csv.gz"
_HORIZONS = (1, 2, 3, 5)


def _universe_medians(universe, horizons) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    for h in horizons:
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


def _concurrence_bucket(n: int) -> str:
    """How many distinct detectors fired on this name, this day."""
    if n <= 1:
        return "1"
    return "2" if n == 2 else "3plus"


def run(*, src: str = _IN_DEFAULT, sample: int = 300, min_bars: int = 400) -> None:
    from app.core.db import SessionLocal

    path = Path(src)
    if not path.exists():
        print(f"Missing {path}. Run app.scripts.conditional_screen_replay first.")
        return

    db = SessionLocal()
    try:
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
    finally:
        db.close()
    closes = {s.stock_id: s.closes for s in universe}
    logger.info(f"[shorthz] {len(closes)} stocks reloaded for rejoin")

    umed = _universe_medians(universe, _HORIZONS)
    logger.info("[shorthz] universe medians ready for h=1,2,3,5")

    # Pass 1 — how many distinct detectors fired per (stock, bar).
    concur: dict[tuple[int, int], set[str]] = defaultdict(set)
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            concur[(int(r["stock_id"]), int(r["bar_i"]))].add(r["detector"])
    conc_n = {k: len(v) for k, v in concur.items()}
    logger.info(f"[shorthz] concurrence map: {len(conc_n):,} (stock, bar) points")

    # One open handle per horizon: the rows are written in a single streaming
    # pass, so a `with` per file would mean re-reading the 730k-row input four
    # times. The try/finally below closes them all.
    writers = {}
    handles = {}
    for h in _HORIZONS:
        fh = gzip.open(  # noqa: SIM115 — closed in the finally, see above
            _OUT_TMPL.format(h=h), "wt", newline="", encoding="utf-8"
        )
        w = csv.writer(fh)
        w.writerow((
            "detector", "tone", "date", "stock_id", "bar_i", "horizon",
            "hit", "excess", "period", *CONDITION_COLUMNS, "concurrence",
        ))
        handles[h], writers[h] = fh, w

    # Absolute vs market-neutral tallies, per (detector, horizon).
    abs_hits: Counter = Counter()
    mn_hits: Counter = Counter()
    tot: Counter = Counter()
    kept = skipped = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                sid, bi = int(r["stock_id"]), int(r["bar_i"])
                c = closes.get(sid)
                if c is None or bi >= len(c) or c[bi] <= 0:
                    skipped += 1
                    continue
                sign = 1.0 if r["tone"] == "bull" else -1.0
                cb = _concurrence_bucket(conc_n.get((sid, bi), 1))
                for h in _HORIZONS:
                    if bi + h >= len(c):
                        continue
                    fwd = c[bi + h] / c[bi] - 1.0
                    bench = umed[h].get(r["date"])
                    if bench is None:
                        continue
                    abs_ex = sign * fwd
                    mn_ex = sign * (fwd - bench)
                    key = (r["detector"], h)
                    tot[key] += 1
                    abs_hits[key] += 1 if abs_ex > 0 else 0
                    mn_hits[key] += 1 if mn_ex > 0 else 0
                    writers[h].writerow((
                        r["detector"], r["tone"], r["date"], sid, bi, h,
                        1 if mn_ex > 0 else 0, f"{mn_ex:.6f}", r["period"],
                        *(r[k] for k in CONDITION_COLUMNS), cb,
                    ))
                kept += 1
    finally:
        for fh in handles.values():
            fh.close()

    print(f"\nRe-scored {kept:,} signals ({skipped:,} unmappable) at h=1,2,3,5.")
    print("\n" + "=" * 96)
    print("ABSOLUTE vs MARKET-NEUTRAL hit rate — the gap between the columns IS beta.")
    print("Anything the ABS column has above 50 that MN does not, you would have got")
    print("by simply being long. Only the MN column is evidence the detector adds")
    print("something. (Bear-tone signals are sign-flipped, so a rising market pushes")
    print("their absolute rate DOWN — read bull and bear detectors accordingly.)")
    print("=" * 96)
    dets = sorted({d for d, _ in tot})
    head = f"{'detector':<22}" + "".join(f"{'h' + str(h) + ' abs/mn':>16}" for h in _HORIZONS)
    print(head)
    print("-" * len(head))
    for d in dets:
        line = f"{d:<22}"
        for h in _HORIZONS:
            n = tot[(d, h)]
            if not n:
                line += f"{'—':>16}"
                continue
            a = 100.0 * abs_hits[(d, h)] / n
            m = 100.0 * mn_hits[(d, h)] / n
            line += f"{a:>7.1f} /{m:>7.1f}"
        print(line)

    n_all = sum(tot.values())
    if n_all:
        a_all = 100.0 * sum(abs_hits.values()) / n_all
        m_all = 100.0 * sum(mn_hits.values()) / n_all
        print("-" * len(head))
        print(f"{'ALL (pooled)':<22}{a_all:>7.1f} /{m_all:>7.1f}"
              f"   <- pooled across horizons; gap = {a_all - m_all:+.1f}pp of beta")

    print("\nPer-horizon grids written. Test each with:")
    for h in _HORIZONS:
        print(f"  PYTHONPATH=. python -m app.scripts.conditional_screen_grid "
              f"--src {_OUT_TMPL.format(h=h)} --out app/data/conditional_screen_report_h{h}.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", default=_IN_DEFAULT)
    p.add_argument("--sample", type=int, default=300)
    p.add_argument("--min-bars", type=int, default=400)
    a = p.parse_args()
    run(src=a.src, sample=a.sample, min_bars=a.min_bars)
