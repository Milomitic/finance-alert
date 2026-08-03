"""The honest half of the conditional screen: many hypotheses, counted.

Reads the rows written by `conditional_screen_replay` and asks, for every
(detector x condition x bucket): does the detector's market-neutral hit rate
in this state differ from its rate in the OTHER states of the same condition?

Testing ~8 conditions x 3 buckets x ~15 detectors is several hundred tests.
At alpha=0.05 roughly one in twenty comes back "significant" from nothing at
all, so a raw p-value here means almost nothing — the screen would always
produce winners, and picking the prettiest is how the last five studies would
have "found" edges that were not there. Three defences, all applied:

1. BENJAMINI-HOCHBERG FDR over the WHOLE grid. Every cell tested is counted,
   including the ones that came back flat. The q-value answers the question
   that actually matters: "if I act on this, what share of findings like it
   are false?" Breadth of search becomes a declared parameter instead of a
   hidden liberty.

2. EFFECTIVE SAMPLE, not nominal. Signals from one name inside one forward
   window are not independent observations — the same move is being counted
   repeatedly. Rows are collapsed into episodes of (stock, bar // horizon) and
   every interval and test is sized on the episode count. The nominal count is
   still printed, because the gap between the two is itself the finding: it is
   routinely an order of magnitude, and the 2026-06-10 study named that
   inflation as one reason its residual effect looked bigger than it was.

3. MINIMUM DETECTABLE EFFECT per cell. A flat result from 80 episodes is not
   evidence of absence, it is absence of evidence. Each row reports the effect
   it had the power to see, so "no effect" and "no power" stay distinguishable
   — the same power-first discipline as `quality_conditional_outcomes`.

Plus a fourth, which is not statistics but design: the `regime` condition is a
NEGATIVE CONTROL. The 2026-06-10 study established, with an adversarial
verification pass, that under a tone-symmetric benchmark no detector has a
credible regime effect. Its expected result here is therefore "nothing
survives". If it DOES survive, the pipeline is wrong and every other survivor
in the same run is void. That check is printed before the results, not after,
because a broken pipeline makes the rest of the output not worth reading.

Reported but never auto-adopted: a survivor here has passed a screen, not the
gate. Adoption still requires the cascade the regime study established — OOS
sign and magnitude, adversarial verification including the tone-condition
correlation that unmasked the trend_pullback artifact, and only then a block
in signal_calibration.json.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.conditional_screen_grid
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_IN_DEFAULT = "app/data/conditional_screen_rows.csv.gz"
_OUT_DEFAULT = "app/data/conditional_screen_report.json"

# Below this many EPISODES a cell is not tested at all — it would only add
# noise to the FDR denominator and could never clear it anyway.
_MIN_EPISODES = 40
# Benjamini-Hochberg target: share of the reported survivors we accept as false.
_FDR_Q = 0.10
# Power target for the MDE column (80% power, two-sided alpha 0.05).
_Z_ALPHA, _Z_POWER = 1.959964, 0.841621

_CONTROL_CONDITION = "regime"

# Conditions whose value is IDENTICAL for every stock on a given date.
#
# This distinction was missing in the first version and it produced nine
# false survivors, so it is worth stating plainly. Collapsing rows into
# per-stock episodes corrects the clustering WITHIN a name — but on 2015-03-12
# there is one VIX, one credit spread, one breadth reading, shared by all 300
# names. Thousands of "independent stock-episodes" are then a handful of
# independent draws of the CONDITION: measured on the real data, 4 to 13
# contiguous blocks across ten years.
#
# So for these, the unit of analysis is the time block: compute the in-bucket
# minus out-of-bucket hit difference within each block, then test those
# differences against zero. Everything that survived the row-level test
# collapsed under this, one of them reversing sign outright — a textbook
# Simpson's paradox, and a reminder that a big n is not a large sample.
_MARKET_WIDE = frozenset({"vix_level", "vix_chg5", "curve", "credit", "breadth"})
# Below this many blocks a market-wide condition cannot be tested at all.
_MIN_BLOCKS = 5


def _phi(z: float) -> float:
    """Standard normal CDF. scipy is not a dependency of this project."""
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def _two_proportion_p(h1: int, n1: int, h2: int, n2: int) -> tuple[float, float]:
    """Two-sided p-value and z for H0: p1 == p2. (1.0, 0.0) when undefined."""
    if n1 < 2 or n2 < 2:
        return (1.0, 0.0)
    p1, p2 = h1 / n1, h2 / n2
    pool = (h1 + h2) / (n1 + n2)
    denom = pool * (1 - pool) * (1 / n1 + 1 / n2)
    if denom <= 0:
        return (1.0, 0.0)
    z = (p1 - p2) / math.sqrt(denom)
    return (2.0 * (1.0 - _phi(abs(z))), z)


def _wilson(hits: float, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = hits / n
    z2 = _Z_ALPHA * _Z_ALPHA
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (_Z_ALPHA * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _mde(n1: int, n2: int, p: float = 0.5) -> float:
    """Smallest difference in percentage points this cell could detect at 80%
    power. Large MDE + flat result = the cell says nothing, not 'no effect'."""
    if n1 < 2 or n2 < 2:
        return float("inf")
    return (_Z_ALPHA + _Z_POWER) * math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) * 100.0


def _bh(pvals: list[float], q: float) -> tuple[list[float], float | None]:
    """Benjamini-Hochberg. Returns (per-test q-values, largest p that passes).

    q-values are made monotone the standard way: stepping down from the
    largest, each keeps the smallest adjusted value seen so far."""
    m = len(pvals)
    if m == 0:
        return ([], None)
    order = sorted(range(m), key=lambda i: pvals[i])
    qv = [1.0] * m
    running = 1.0
    threshold: float | None = None
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        adj = min(1.0, pvals[i] * m / rank)
        running = min(running, adj)
        qv[i] = running
        if running <= q and threshold is None:
            threshold = pvals[i]
    return (qv, threshold)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Lentz's method)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-9:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _t_two_sided_p(t: float, df: int) -> float:
    """Two-sided Student-t p-value. Needed because the block-level test runs on
    a handful of observations, where the normal approximation is far too
    generous — which is exactly the regime where a false finding is born."""
    if df < 1 or not math.isfinite(t):
        return 1.0
    return _betai(df / 2.0, 0.5, df / (df + t * t))


def _block_test(diffs: list[float]) -> tuple[float, float, float]:
    """One-sample t-test on per-block differences. Returns (mean, t, p)."""
    n = len(diffs)
    if n < 3:
        return (float("nan"), 0.0, 1.0)
    mu = sum(diffs) / n
    var = sum((x - mu) ** 2 for x in diffs) / (n - 1)
    if var <= 0:
        return (mu, 0.0, 1.0)
    t = mu / math.sqrt(var / n)
    return (mu, t, _t_two_sided_p(t, n - 1))


def _blocks(months: set[str]) -> list[list[str]]:
    """Group calendar months into runs with no gap. A market-wide condition
    persists for months at a time, so one run is ONE independent occurrence of
    that state — not one per stock per day."""
    out: list[list[str]] = []
    cur: list[str] = []
    prev: int | None = None
    for m in sorted(months):
        idx = int(m[:4]) * 12 + int(m[5:7])
        if prev is not None and idx - prev > 1:
            out.append(cur)
            cur = []
        cur.append(m)
        prev = idx
    if cur:
        out.append(cur)
    return out


@dataclass
class _Cell:
    hits: int = 0
    n: int = 0
    episodes: set[tuple[int, int]] = field(default_factory=set)
    bull: int = 0
    train_hits: int = 0
    train_n: int = 0
    hold_hits: int = 0
    hold_n: int = 0
    excess_sum: float = 0.0
    # month -> [hits, n]; the substrate for the block-level test.
    by_month: dict[str, list[int]] = field(default_factory=dict)

    def add(self, row: dict, ep: tuple[int, int]) -> None:
        hit = int(row["hit"])
        self.hits += hit
        self.n += 1
        self.episodes.add(ep)
        if row["tone"] == "bull":
            self.bull += 1
        self.excess_sum += float(row["excess"])
        slot = self.by_month.setdefault(row["date"][:7], [0, 0])
        slot[0] += hit
        slot[1] += 1
        if row["period"] == "holdout":
            self.hold_hits += hit
            self.hold_n += 1
        else:
            self.train_hits += hit
            self.train_n += 1


def run(*, src: str = _IN_DEFAULT, out: str = _OUT_DEFAULT, q: float = _FDR_Q) -> None:
    path = Path(src)
    if not path.exists():
        print(f"Missing {path}. Run app.scripts.conditional_screen_replay first.")
        return

    # (detector, condition, bucket) -> cell
    cells: dict[tuple[str, str, str], _Cell] = defaultdict(_Cell)
    conditions: list[str] = []
    total_rows = 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fixed = {"detector", "tone", "date", "stock_id", "bar_i",
                 "horizon", "hit", "excess", "period"}
        conditions = [c for c in (reader.fieldnames or []) if c not in fixed]
        for row in reader:
            total_rows += 1
            h = int(row["horizon"]) or 1
            ep = (int(row["stock_id"]), int(row["bar_i"]) // h)
            det = row["detector"]
            for cond in conditions:
                bucket = row[cond]
                if bucket == "na":
                    continue
                cells[(det, cond, bucket)].add(row, ep)

    if not cells:
        print("No usable rows.")
        return

    # Build the test grid: each cell against the OTHER buckets of the same
    # (detector, condition). That contrast is the hypothesis actually being
    # asked — "does THIS state differ from the rest?" — and keeps every test
    # inside one detector, so a detector's overall skill cannot leak in.
    by_det_cond: dict[tuple[str, str], list[str]] = defaultdict(list)
    for det, cond, bucket in cells:
        by_det_cond[(det, cond)].append(bucket)

    tests: list[dict] = []
    for (det, cond), buckets in sorted(by_det_cond.items()):
        if len(buckets) < 2:
            continue
        for bucket in sorted(buckets):
            cell = cells[(det, cond, bucket)]
            others = [cells[(det, cond, b)] for b in buckets if b != bucket]
            o_hits = sum(c.hits for c in others)
            o_n = sum(c.n for c in others)
            o_eps = len({e for c in others for e in c.episodes})
            n_eps = len(cell.episodes)
            if n_eps < _MIN_EPISODES or o_eps < _MIN_EPISODES:
                continue
            rate = 100.0 * cell.hits / cell.n
            o_rate = 100.0 * o_hits / o_n
            # Point estimates from all rows; the TEST is sized on episodes,
            # scaling the hit counts down proportionally so the rate is kept.
            eh, en = round(cell.hits * n_eps / cell.n), n_eps
            oh, on = round(o_hits * o_eps / o_n), o_eps
            lo, hi = _wilson(eh, en)
            # The unit of analysis depends on how the condition varies. A
            # per-stock condition (sector RS, ATR regime) genuinely differs
            # across names on the same day, so stock-episodes are independent
            # draws and the proportion test applies. A market-wide one does
            # not — see _MARKET_WIDE — so it is tested across time blocks.
            block_mean = block_t = None
            n_blocks = 0
            if cond in _MARKET_WIDE:
                o_months: dict[str, list[int]] = {}
                for c in others:
                    for mth, (mh, mn) in c.by_month.items():
                        slot = o_months.setdefault(mth, [0, 0])
                        slot[0] += mh
                        slot[1] += mn
                diffs: list[float] = []
                for grp in _blocks(set(cell.by_month)):
                    ih = sum(cell.by_month[m][0] for m in grp)
                    inn = sum(cell.by_month[m][1] for m in grp)
                    oh_b = sum(o_months[m][0] for m in grp if m in o_months)
                    on_b = sum(o_months[m][1] for m in grp if m in o_months)
                    if inn >= 30 and on_b >= 30:
                        diffs.append(100.0 * ih / inn - 100.0 * oh_b / on_b)
                n_blocks = len(diffs)
                if n_blocks < _MIN_BLOCKS:
                    continue
                block_mean, block_t, p = _block_test(diffs)
                z = block_t
            else:
                p, z = _two_proportion_p(eh, en, oh, on)
            d_train = (100.0 * cell.train_hits / cell.train_n) if cell.train_n else None
            d_hold = (100.0 * cell.hold_hits / cell.hold_n) if cell.hold_n else None
            o_train = sum(c.train_hits for c in others), sum(c.train_n for c in others)
            o_hold = sum(c.hold_hits for c in others), sum(c.hold_n for c in others)
            dt = (d_train - 100.0 * o_train[0] / o_train[1]) if (d_train is not None and o_train[1]) else None
            dh = (d_hold - 100.0 * o_hold[0] / o_hold[1]) if (d_hold is not None and o_hold[1]) else None
            tests.append({
                "detector": det, "condition": cond, "bucket": bucket,
                "rate": round(rate, 2), "other_rate": round(o_rate, 2),
                "delta": round(rate - o_rate, 2),
                "unit": "time_block" if cond in _MARKET_WIDE else "stock_episode",
                "n_blocks": n_blocks,
                "block_delta": round(block_mean, 2) if block_mean is not None else None,
                "block_t": round(block_t, 2) if block_t is not None else None,
                "n_rows": cell.n, "n_episodes": n_eps,
                "other_episodes": o_eps,
                "inflation": round(cell.n / n_eps, 1),
                "ci_lo": round(100 * lo, 2), "ci_hi": round(100 * hi, 2),
                "mde_pp": round(_mde(en, on), 2),
                "p": p, "z": round(z, 2),
                "bull_share": round(100.0 * cell.bull / cell.n, 1),
                "delta_train": round(dt, 2) if dt is not None else None,
                "delta_holdout": round(dh, 2) if dh is not None else None,
                "oos_same_sign": bool(
                    dt is not None and dh is not None and dt != 0
                    and (dt > 0) == (dh > 0)
                ),
                "mean_excess_pct": round(100.0 * cell.excess_sum / cell.n, 3),
            })

    qvals, _ = _bh([t["p"] for t in tests], q)
    for t, qq in zip(tests, qvals, strict=False):
        t["q"] = qq
        t["survives"] = bool(qq <= q and t["oos_same_sign"])

    # ── negative control, printed FIRST ────────────────────────────────
    control = [t for t in tests if t["condition"] == _CONTROL_CONDITION]
    control_survivors = [t for t in control if t["survives"]]
    print(f"\n{'#' * 100}")
    print("#  CONDITIONAL SCREEN — many hypotheses, FDR-corrected")
    print(f"#  rows={total_rows:,}  cells tested={len(tests)}  BH target q<={q}")
    print(f"{'#' * 100}")
    print(f"\nNEGATIVE CONTROL ({_CONTROL_CONDITION}, {len(control)} cells) — "
          "the 2026-06-10 study says this must come back null.")
    if control_survivors:
        print("  *** FAILED *** the control produced survivors:")
        for t in control_survivors:
            print(f"      {t['detector']} / {t['bucket']}  delta={t['delta']:+.1f}pp  q={t['q']:.3f}")
        print("  The pipeline is suspect. Do NOT read the results below as findings.")
    else:
        print("  PASSED — no control cell survives. The grid is behaving as expected.")

    survivors = [t for t in tests
                 if t["survives"] and t["condition"] != _CONTROL_CONDITION]
    print(f"\n{'-' * 100}")
    print(f"SURVIVORS (q<={q} AND out-of-sample sign stable): {len(survivors)}")
    print(f"{'-' * 100}")
    if survivors:
        print(f"{'detector':<22}{'condition':<12}{'bucket':<7}{'rate%':>7}{'vs rest':>9}"
              f"{'unit':>13}{'n':>7}{'blkΔ':>7}{'q':>8}{'OOSΔ':>8}")
        for t in sorted(survivors, key=lambda x: x["q"]):
            n_unit = t["n_blocks"] if t["unit"] == "time_block" else t["n_episodes"]
            bd = t["block_delta"]
            print(f"{t['detector']:<22}{t['condition']:<12}{t['bucket']:<7}"
                  f"{t['rate']:>7.1f}{t['delta']:>+9.1f}{t['unit']:>13}{n_unit:>7}"
                  f"{(f'{bd:+.1f}' if bd is not None else '—'):>7}{t['q']:>8.3f}"
                  f"{(t['delta_holdout'] or 0):>+8.1f}")
        print("\nA survivor is a CANDIDATE, not a result. Required next: adversarial")
        print("verification (start with the tone/condition correlation — check the")
        print("bull_share column against the detector's overall tone mix), then a")
        print("confirmation run on a wider universe.")
    else:
        print("  None. Every conditional effect tested is indistinguishable from")
        print("  chance once the number of tests is accounted for.")

    # Power accounting — what the null actually means here.
    underpowered = [t for t in tests if t["mde_pp"] > 10.0]
    print(f"\nPOWER: {len(underpowered)}/{len(tests)} cells could not have detected")
    print("even a 10pp effect. For those, 'flat' means 'no power', not 'no effect'.")
    if tests:
        infl = sorted(t["inflation"] for t in tests)
        print(f"Episode inflation (rows per independent episode): median "
              f"{infl[len(infl) // 2]:.1f}x — the nominal sample overstates by that much.")

    top = sorted(tests, key=lambda x: x["q"])[:15]
    print(f"\n{'-' * 100}\nCLOSEST 15 CELLS (whether or not they survive)\n{'-' * 100}")
    print(f"{'detector':<22}{'condition':<12}{'bucket':<7}{'rate%':>7}{'vs rest':>9}"
          f"{'blkΔ':>7}{'n':>6}{'t/z':>7}{'p':>9}{'q':>8}{'OOS':>6}")
    for t in top:
        n_unit = t["n_blocks"] if t["unit"] == "time_block" else t["n_episodes"]
        bd = t["block_delta"]
        print(f"{t['detector']:<22}{t['condition']:<12}{t['bucket']:<7}"
              f"{t['rate']:>7.1f}{t['delta']:>+9.1f}"
              f"{(f'{bd:+.1f}' if bd is not None else '—'):>7}{n_unit:>6}"
              f"{t['z']:>7.2f}{t['p']:>9.4f}{t['q']:>8.3f}"
              f"{('same' if t['oos_same_sign'] else 'flip'):>6}")
    n_mw = sum(1 for t in tests if t["unit"] == "time_block")
    print(f"\n{n_mw}/{len(tests)} cells are market-wide conditions, tested across")
    print("TIME BLOCKS rather than stock-episodes: on any given date every stock")
    print("shares one VIX and one credit spread, so a 12,000-episode cell can be")
    print("four independent occurrences of the state. Sizing those on stock counts")
    print("is what produced nine false survivors in the first run of this grid.")

    report = {
        "rows": total_rows,
        "cells_tested": len(tests),
        "fdr_q": q,
        "control_condition": _CONTROL_CONDITION,
        "control_passed": not control_survivors,
        "survivors": survivors,
        "all_cells": tests,
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nFull grid written to {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", default=_IN_DEFAULT)
    p.add_argument("--out", default=_OUT_DEFAULT)
    p.add_argument("--q", type=float, default=_FDR_Q)
    a = p.parse_args()
    run(src=a.src, out=a.out, q=a.q)
