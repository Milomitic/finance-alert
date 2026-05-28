"""Chart-pattern reversal (geometric): a double bottom / double top whose
neckline has been broken by price - the classic completion that validates the
pattern. Source: Bulkowski. Confirmed: pattern structure + neckline break."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, concave, score_v2
from app.signals.events import Event

# Forza anchor for pattern_amplitude = the chart_pattern event magnitude
# (already 0..1; the extractor hard-codes ~0.6 for many patterns). Anchors live
# in those 0..1 units: a 0.80-amplitude pattern reads strong (→ ~0.88).
_PATTERN_AMPLITUDE_ANCHORS = (0.40, 0.65, 0.80, 0.92)

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
        return SignalMatch(name=self.name, tone=tone, confidence=strength,
                           strength=strength, probability=probability,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors,
                           annotations=annotations)
