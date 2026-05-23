"""ADX Trend Confirmation (B13): a strong directional regime (ADX high with
+DI/-DI alignment) confirmed by a breakout in the same direction - a
trend-following entry with a strength filter. Source: Wilder (1978) ADX/DMI.
Confirmed: adx_trend + breakout."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

_BREAK_WINDOW_DAYS = 4


class AdxConfirmation:
    name = "adx_confirmation"
    tone = "bull"
    sources = ["Wilder (1978) ADX/DMI + breakout confirmation"]
    min_bars = 30

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        adxs = [e for e in events if e.type == "adx_trend"]
        if not adxs:
            return None
        a = adxs[-1]
        tone = a.direction or "bull"
        # Confirmation: a breakout in the same direction on/around the adx bar.
        bo_same = any(e.type == "breakout" and e.direction == tone and e.date == a.date for e in events)
        bo_after = find_after(events, "breakout", after=a.date, within_days=_BREAK_WINDOW_DAYS, direction=tone)
        bo_before = any(e.type == "breakout" and e.direction == tone for e in events)
        if not (bo_same or bo_after or bo_before):
            return None
        factors = {
            "adx_strength": clamp01(a.magnitude or 0.0),
            "di_spread": clamp01(abs((a.payload.get("plus_di") or 0) - (a.payload.get("minus_di") or 0)) / 25.0),
            "breakout": 1.0,   # gate (display only)
        }
        conf = score(factors, {"adx_strength": 1.0, "di_spread": 0.6})
        adx_v = a.payload.get("adx")
        chain = [
            {"date": a.date, "label": f"Trend forte (ADX) {tone}",
             "detail": f"ADX {adx_v} con DI allineati"},
            {"date": a.date, "label": "Conferma breakout",
             "detail": "rottura nel verso del trend"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=a.date, chain=chain, invalidation=None, factors=factors)
