"""Hidden RSI Divergence (B7): a trend-CONTINUATION signal.

Bull hidden: price makes a higher low while RSI makes a lower low -- in an
uptrend this signals the momentum dip is shallow and the trend will resume up.
Bear hidden: price makes a lower high while RSI makes a higher high -- in a
downtrend the momentum bounce is weak and the trend will resume down.

Unlike regular (reversal) divergence which rewards counter-trend setups, this
detector rewards WITH-trend alignment: a bull hidden divergence is most
credible when ctx.trend_sign > 0, and a bear hidden divergence when < 0.

Source: Hidden divergence (trend-continuation), momentum literature."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_WITH_TREND = 1.0
_COUNTER_TREND = 0.4


class HiddenDivergence:
    name = "hidden_divergence"
    tone = "bull"
    sources = ["Hidden divergence (trend-continuation), momentum literature"]
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        divs = [e for e in events if e.type == "hidden_divergence"]
        if not divs:
            return None
        d = divs[-1]
        tone = d.direction or "bull"
        # With-trend alignment: bull hidden is credible in uptrend, bear in downtrend
        aligned = (tone == "bull" and ctx.trend_sign > 0) or (tone == "bear" and ctx.trend_sign < 0)
        factors = {
            "divergence_amplitude": clamp01(d.magnitude or 0.0),
            "trend_alignment": _WITH_TREND if aligned else _COUNTER_TREND,
        }
        conf = score(factors, {"divergence_amplitude": 1.0, "trend_alignment": 1.2})
        pivots = d.payload.get("pivot_dates") or [d.date, d.date]
        chain = [
            {"date": pivots[0], "label": "Pivot iniziale",
             "detail": "estremo di prezzo iniziale (minimo/massimo)"},
            {"date": d.date, "label": f"Divergenza nascosta {tone} (continuazione)",
             "detail": "prezzo e RSI divergono nella stessa direzione del trend -- continuazione attesa"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=d.date, chain=chain, invalidation=None,
                           factors=factors)
