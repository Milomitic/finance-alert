"""RSI Regular Divergence: price makes a lower low while RSI makes a higher low
(bull), or price a higher high while RSI a lower high (bear) - a classic
reversal setup. Source: Wilder, "New Concepts in Technical Trading Systems"
(1978). Consumes the rsi_divergence event produced by the extractor."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_COUNTER_TREND_BONUS = 1.0
_WITH_TREND = 0.5


class RsiDivergence:
    name = "rsi_divergence"
    tone = "bull"
    sources = ['Wilder, "New Concepts in Technical Trading Systems" (1978)']
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        divs = [e for e in events if e.type == "rsi_divergence"]
        if not divs:
            return None
        d = divs[-1]
        tone = d.direction or "bull"
        rsi_pair = d.payload.get("rsi") or []
        counter = (tone == "bull" and ctx.trend_sign <= 0) or (tone == "bear" and ctx.trend_sign >= 0)
        extremity = 0.0
        if len(rsi_pair) == 2:
            if tone == "bull":
                extremity = clamp01((40.0 - min(rsi_pair)) / 25.0)
            else:
                extremity = clamp01((max(rsi_pair) - 60.0) / 25.0)
        factors = {
            "divergence_amplitude": clamp01(d.magnitude or 0.0),
            "extremity": extremity,
            "trend_context": _COUNTER_TREND_BONUS if counter else _WITH_TREND,
        }
        conf = score(factors, {"divergence_amplitude": 1.0, "extremity": 0.8, "trend_context": 1.0})
        pivots = d.payload.get("pivot_dates") or [d.date, d.date]
        chain = [
            {"date": pivots[0], "label": "Primo minimo/massimo",
             "detail": "estremo di prezzo iniziale"},
            {"date": d.date, "label": f"Divergenza RSI {tone}",
             "detail": "prezzo e RSI divergono (setup di inversione)"},
        ]
        close_by_date = {str(row.date)[:10]: float(row.close)
                         for row in ohlcv.itertuples(index=False)}
        points = [{"date": dt, "price": close_by_date[dt]}
                  for dt in pivots if dt in close_by_date]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=d.date, chain=chain, invalidation=None,
                           factors=factors,
                           annotations={"levels": [], "points": points})
