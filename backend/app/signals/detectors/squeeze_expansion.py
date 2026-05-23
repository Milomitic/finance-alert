"""Volatility Squeeze Expansion: Bollinger Bands contract inside Keltner
Channels (a squeeze = energy build-up), then expand; the breakout resolves in
the expansion's direction. Source: Bollinger (2001); TTM Squeeze (Carter,
"Mastering the Trade"). Consumes bb_squeeze + bb_expansion events."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

_EXPAND_WINDOW_DAYS = 15
_TIGHTNESS_REF = 1.5


class SqueezeExpansion:
    name = "squeeze_expansion"
    tone = "bull"
    sources = ['Bollinger (2001); TTM Squeeze (Carter, "Mastering the Trade")']
    min_bars = 25

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        squeezes = [e for e in events if e.type == "bb_squeeze"]
        if not squeezes:
            return None
        sq = squeezes[-1]
        exp = find_after(events, "bb_expansion", after=sq.date, within_days=_EXPAND_WINDOW_DAYS)
        if exp is None:
            return None
        tone = exp.direction or ("bull" if ctx.trend_sign >= 0 else "bear")
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "tightness": clamp01((sq.magnitude or 1.0) / _TIGHTNESS_REF),
            "expansion_strength": clamp01((exp.magnitude or 0.0) / 0.06),
            "trend_alignment": 1.0 if trend_aligned else 0.5,
        }
        conf = score(factors, {"tightness": 0.8, "expansion_strength": 1.0, "trend_alignment": 0.8})
        chain = [
            {"date": sq.date, "label": "Compressione (squeeze)",
             "detail": "Bollinger dentro Keltner: volatilita compressa"},
            {"date": exp.date, "label": f"Espansione {tone}",
             "detail": "le bande si riaprono: rilascio nel verso del trend"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=exp.date, chain=chain, invalidation=None,
                           factors=factors)
