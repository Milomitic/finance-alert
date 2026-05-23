"""Chart-pattern reversal (geometric): a double bottom / double top whose
neckline has been broken by price - the classic completion that validates the
pattern. Source: Bulkowski. Confirmed: pattern structure + neckline break."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_PATTERN_IT = {
    "double_bottom": "Doppio minimo",
    "double_top": "Doppio massimo",
    "inverse_head_shoulders": "Testa-spalle inverso",
    "head_shoulders": "Testa-spalle",
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
            "pattern_amplitude": clamp01(p.magnitude or 0.0),
            "neckline_break": 1.0,   # gate (display only)
        }
        conf = score(factors, {"pattern_amplitude": 1.0})
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
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors)
