"""52-Week-High Momentum: price at/near its 52-week high within an uptrend - a
documented momentum anomaly. Source: George & Hwang, "The 52-Week High and
Momentum Investing" (J. Finance 2004). Computes proximity directly (no event)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_WINDOW = 252
_NEAR_THRESHOLD = 0.97


class High52Momentum:
    name = "high52_momentum"
    tone = "bull"
    sources = ['George & Hwang, "The 52-Week High and Momentum Investing" (J. Finance 2004)']
    min_bars = 60

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        high = ohlcv["high"].astype(float)
        low = ohlcv["low"].astype(float)
        window = min(_WINDOW, len(ohlcv))
        hi_52 = float(high.iloc[-window:].max())
        lo_52 = float(low.iloc[-window:].min())
        last = ctx.last_close
        if hi_52 <= 0:
            return None
        proximity = last / hi_52
        if proximity < _NEAR_THRESHOLD or ctx.trend_sign <= 0:
            return None
        rng = hi_52 - lo_52
        momentum = clamp01((last - lo_52) / rng) if rng > 0 else 0.0
        factors = {
            "proximity": clamp01((proximity - _NEAR_THRESHOLD) / (1.0 - _NEAR_THRESHOLD)),
            "trend": 1.0 if ctx.trend_sign > 0 else 0.0,
            "momentum": momentum,
        }
        conf = score(factors, {"proximity": 1.0, "trend": 0.8, "momentum": 0.8})
        last_date = str(ohlcv["date"].iloc[-1])[:10]
        chain = [
            {"date": last_date, "label": "Vicino al massimo 52 settimane",
             "detail": f"prezzo a {proximity * 100:.1f}% del massimo a 52w"},
            {"date": last_date, "label": "Trend rialzista",
             "detail": "EMA lunga in salita: momentum confermato"},
        ]
        invalidation = {"level": lo_52, "reason": "rottura del minimo a 52 settimane"}
        return SignalMatch(name=self.name, tone="bull", confidence=conf,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors)
