"""Does Qualità matter CONDITIONALLY — specifically after a reversal fires?

THE QUESTION, AND WHY IT IS NOT ALREADY ANSWERED
────────────────────────────────────────────────
Three studies in this repo came back negative, and it is easy to read them as
having settled this. They did not:

- `confirmation_outcomes` tested co-temporal confirmations of the SAME
  technical event. Same lens.
- `fit_signal_calibration` tested per-FACTOR adjustments, one factor at a time.
- `score_ic_backtest` tested the Qualità composite UNCONDITIONALLY — does a
  high score predict returns across the whole universe? It does not (IC ~0).

None of them asked whether quality predicts returns *given that a technical
reversal has just fired*. An unconditional null does not imply a conditional
one: "quality does not time the market" and "quality separates which
panic-sells bounce" are different claims, and only the first has been tested.

That is the one opening left in the "buy a strong company when it panics"
idea, so it deserves a real test rather than an opinion.

WHY THIS SCRIPT LEADS WITH POWER
────────────────────────────────
Run today, the answer is "not enough data", and that matters more than any
number it could print. `oversold_reversal` — the detector whose scenario this
is really about — has NINE matured outcomes joinable to a point-in-time
quality score. Split into terciles that is three per cell.

So the script computes the MINIMUM DETECTABLE EFFECT first and reports every
split against it. A difference smaller than the MDE is not evidence of
absence; it is the absence of evidence, and the two get confused exactly when
someone is hoping for a particular answer. Printing a hit-rate gap without
that bar next to it would manufacture a false conclusion — which is the
failure mode the three studies above exist to prevent.

Re-run as outcomes accrue. It becomes conclusive on its own.

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.quality_conditional_outcomes
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import select

from app.core import db as core_db
from app.models import ScoreHistory, SignalOutcome

# How far back a quality snapshot may be and still describe the company as it
# was when the signal fired. Scores are recomputed per scan, so a fortnight is
# generous; beyond that the snapshot is describing a different situation.
_LOOKBACK_DAYS = 14
# Below this a tercile cell is not a sample, and reporting a rate from it
# invites reading noise as signal.
_MIN_CELL = 30


def _min_detectable_effect(n_per_cell: int, base_rate: float = 0.5) -> float:
    """Smallest hit-rate gap two cells of this size could distinguish.

    Standard two-proportion test at alpha=0.05, power=0.80 (z=1.96 + 0.84).
    Returned in percentage points — the unit the results are read in.
    """
    if n_per_cell < 2:
        return float("inf")
    se = math.sqrt(2.0 * base_rate * (1.0 - base_rate) / n_per_cell)
    return 2.8 * se * 100.0


def main() -> None:
    with core_db.SessionLocal() as db:
        outcomes = db.execute(select(SignalOutcome)).scalars().all()
        # lens='qualita' explicitly: score_history holds BOTH lenses, and
        # mixing the technical composite in here would silently answer a
        # different question than the one asked.
        history = db.execute(
            select(ScoreHistory.stock_id, ScoreHistory.captured_on, ScoreHistory.composite)
            .where(ScoreHistory.lens == "qualita")
        ).all()

    # stock -> [(date, composite)], newest first, so the join takes the most
    # recent snapshot at or before the signal.
    by_stock: dict[int, list] = defaultdict(list)
    for stock_id, captured_on, composite in history:
        if composite is not None:
            by_stock[stock_id].append((captured_on, float(composite)))
    for rows in by_stock.values():
        rows.sort(key=lambda r: r[0], reverse=True)

    def quality_at(stock_id: int, on) -> float | None:
        for d, comp in by_stock.get(stock_id, []):
            if d <= on:
                return comp if (on - d).days <= _LOOKBACK_DAYS else None
        return None

    joined: dict[str, list] = defaultdict(list)
    for o in outcomes:
        q = quality_at(o.stock_id, o.signal_date)
        if q is None:
            continue
        # Market-neutral: an absolute win during a rising market says nothing
        # about the setup. This is the same measure the warehouse uses for
        # every other study here.
        hit = o.mkt_neutral_hit if o.mkt_neutral_hit is not None else o.abs_hit
        if hit is None:
            continue
        joined[o.detector].append((q, bool(hit), o.mkt_neutral_excess))

    print("Does Qualità separate winners CONDITIONAL on a signal firing?")
    print("=" * 74)
    print(f"quality snapshot within {_LOOKBACK_DAYS} days before the signal; "
          f"market-neutral outcome\n")

    if not joined:
        print("No outcomes could be joined to a point-in-time quality score.")
        print("score_history has to cover the dates the signals fired on.")
        return

    verdicts = []
    for detector, rows in sorted(joined.items(), key=lambda kv: -len(kv[1])):
        n = len(rows)
        rows.sort(key=lambda r: r[0])
        cut = n // 3
        low, high = rows[:cut], rows[-cut:] if cut else []
        print(f"── {detector}  (n={n})")

        if cut < _MIN_CELL:
            need = _MIN_CELL * 3
            print(f"   NOT TESTABLE — {cut} per tercile, need >= {_MIN_CELL} "
                  f"(so >= {need} outcomes). Nothing is concluded here.\n")
            verdicts.append((detector, n, None, None))
            continue

        lo_rate = sum(1 for _, h, _ in low if h) / len(low) * 100
        hi_rate = sum(1 for _, h, _ in high if h) / len(high) * 100
        gap = hi_rate - lo_rate
        mde = _min_detectable_effect(cut)

        lo_exc = [e for _, _, e in low if e is not None]
        hi_exc = [e for _, _, e in high if e is not None]
        lo_mean = sum(lo_exc) / len(lo_exc) * 100 if lo_exc else float("nan")
        hi_mean = sum(hi_exc) / len(hi_exc) * 100 if hi_exc else float("nan")

        print(f"   quality bottom third : hit {lo_rate:5.1f}%   excess {lo_mean:+6.2f}%")
        print(f"   quality top third    : hit {hi_rate:5.1f}%   excess {hi_mean:+6.2f}%")
        print(f"   gap {gap:+.1f}pp   vs minimum detectable {mde:.1f}pp at n={cut}/cell")

        if abs(gap) >= mde:
            print("   -> SIGNAL: the gap clears the detection bar. Worth a "
                  "proper out-of-sample test before believing it.\n")
            verdicts.append((detector, n, gap, True))
        else:
            print("   -> INCONCLUSIVE: the gap is smaller than this sample can "
                  "resolve. NOT evidence of no effect.\n")
            verdicts.append((detector, n, gap, False))

    print("=" * 74)
    testable = [v for v in verdicts if v[3] is not None]
    if not testable:
        print("VERDICT: no detector has enough joinable outcomes to test yet.")
        print("Nothing here supports OR refutes the conditional-quality idea.")
        print("Re-run as the warehouse accrues; the script becomes conclusive "
              "on its own.")
    elif any(v[3] for v in testable):
        print("VERDICT: at least one detector clears the detection bar — see "
              "above. Treat as a lead, not a finding: this is one in-sample "
              "look, and the bar for changing a score is out-of-sample.")
    else:
        print("VERDICT: nothing clears the detection bar at current sample "
              "sizes. That is 'cannot tell', not 'no effect'.")


if __name__ == "__main__":
    main()
