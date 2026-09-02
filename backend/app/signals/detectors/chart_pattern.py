"""Chart-pattern reversal (geometric): a double bottom / double top whose
neckline has been broken by price - the classic completion that validates the
pattern. Source: Bulkowski. Confirmed: pattern structure + neckline break."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, concave, score_v2
from app.signals.events import Event

# Forza anchors for pattern_amplitude = the chart_pattern event magnitude, i.e.
# the pattern's height as a fraction of price. This is the ONLY strength factor
# this detector weighs (weight 1.0), so these anchors ARE the Forza curve.
#
# They used to be (0.40, 0.65, 0.80, 0.92) — values that ask for a figure whose
# height is 40-92% of the share price. No such pattern exists. Measured over
# the whole universe (1,041 patterns, all seven families):
#
#     p10   p25   p50   p75   p85   p95   p99   max
#    .054  .070  .094  .136  .165  .234  .321  .564
#
# so the old anchors mapped the MEDIAN pattern to Forza 10.6, and exactly ONE
# pattern in 1,041 could clear the 60 emission gate. The four families that
# measure their amplitude honestly were therefore silent — every alert this
# detector ever produced was a triangle riding a hard-coded 0.6/0.55 (see the
# triangle note in signals/chart_patterns.py).
#
# WHAT GROUNDS THESE NUMBERS, AND WHAT DOES NOT. The convention elsewhere in
# this package is that anchors sit at the raw level where the realised forward
# hit-rate crosses 52/56/60% (app.scripts.signal_factor_outcomes). NO SUCH
# STUDY EXISTS for pattern_amplitude, and this repo's rule is that you do not
# invent one. These are placed on the OBSERVED DISTRIBUTION instead — a45 at
# the median, a75 at p85, a88 at p97 — which is the most direct reading of
# "0.45 = a middling example of this factor" that requires no invention.
#
# Say plainly what that buys: Forza here ranks a pattern by HOW BIG IT IS
# relative to other patterns. It is not a probability and carries no claim
# about outcome. That is the honest job of an attention filter, and it is a
# strictly weaker claim than the one the old constants implied.
#
# Consequence to expect: ~27% of detected patterns now clear Forza 60 (before
# the neckline-break confirmation, which filters further), against ~3.6% —
# triangles only — before. Volume goes UP and the mix changes completely.
_PATTERN_AMPLITUDE_ANCHORS = (0.094, 0.165, 0.265, 0.45)

_PATTERN_IT = {
    "double_bottom": "Doppio minimo",
    "double_top": "Doppio massimo",
    "inverse_head_shoulders": "Testa-spalle inverso",
    "head_shoulders": "Testa-spalle",
    "ascending_triangle": "Triangolo ascendente",
    "descending_triangle": "Triangolo discendente",
    "symmetrical_triangle": "Triangolo simmetrico",
}


class ChartPattern:
    name = "chart_pattern"
    tone = "bull"
    sources = ["Bulkowski, Encyclopedia of Chart Patterns - double top/bottom"]
    min_bars = 25

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        pats = [e for e in events if e.type == "chart_pattern"]
        if not pats:
            return None
        p = pats[-1]
        tone = p.direction or "bull"
        neckline = p.payload.get("neckline")
        if not isinstance(neckline, (int, float)) or neckline <= 0:
            return None
        last = ctx.last_close
        # Confirmation: price has broken the neckline in the pattern direction.
        broke = (last > neckline) if tone == "bull" else (last < neckline)
        if not broke:
            return None
        factors = {
            "pattern_amplitude": concave(clamp01(p.magnitude or 0.0), _PATTERN_AMPLITUDE_ANCHORS),
            "neckline_break": 1.0,   # gate (display only)
        }
        # Forza: pattern_amplitude is the only genuine strength factor; the
        # always-1.0 neckline_break gate is excluded from the soft-min cap.
        strength = score_v2(factors, {"pattern_amplitude": 1.0},
                            strength_keys={"pattern_amplitude"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        pat = p.payload.get("pattern", "pattern")
        last_date = str(ohlcv["date"].iloc[-1])[:10]
        chain = [
            {"date": p.date, "label": _PATTERN_IT.get(pat, pat),
             "detail": f"struttura confermata, neckline {neckline:.2f}"},
            {"date": last_date, "label": "Rottura neckline",
             "detail": f"prezzo {last:.2f} oltre la neckline {neckline:.2f}"},
        ]
        invalidation = {"level": float(neckline),
                        "reason": "rientro oltre la neckline (pattern fallito)"}
        pts = p.payload.get("points") or []
        annotations = {
            "levels": [{"label": "Neckline", "price": float(neckline), "kind": "neckline"}],
            "points": [{"date": str(pt["date"])[:10], "price": float(pt["price"])}
                       for pt in pts if isinstance(pt.get("price"), (int, float))],
        }
        return SignalMatch(name=self.name, tone=tone,
                           strength=strength, probability=probability,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors,
                           annotations=annotations)
