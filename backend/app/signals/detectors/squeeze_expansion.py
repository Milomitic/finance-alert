"""Volatility Squeeze Expansion: Bollinger Bands contract inside Keltner
Channels (a squeeze = energy build-up), then expand; the breakout resolves in
the expansion's direction. Source: Bollinger (2001); TTM Squeeze (Carter,
"Mastering the Trade"). Consumes bb_squeeze + bb_expansion events."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, concave, find_after, score_v2
from app.signals.events import Event

_EXPAND_WINDOW_DAYS = 15
# Forza anchors in raw event-magnitude units.
# tightness = Keltner/Bollinger width ratio; >=1.5 = unusually compressed.
_TIGHTNESS_ANCHORS = (0.95, 1.2, 1.5, 2.0)
# expansion_strength = |close-mid|/mid at the band re-open; >=10% = real release.
_EXPANSION_ANCHORS = (0.03, 0.06, 0.10, 0.15)


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
            "tightness": concave(sq.magnitude or 1.0, _TIGHTNESS_ANCHORS),
            "expansion_strength": concave(exp.magnitude or 0.0, _EXPANSION_ANCHORS),
            "trend_alignment": 1.0 if trend_aligned else 0.5,
        }
        weights = {"tightness": 0.8, "expansion_strength": 1.0, "trend_alignment": 0.8}
        # Forza: soft-min over the two STRENGTH factors (tightness + expansion),
        # so a mediocre tightness can't be laundered to 90 by a saturated
        # expansion + alignment — the exact "mediocrity laundering" the study found.
        strength = score_v2(factors, weights,
                            strength_keys={"tightness", "expansion_strength"})
        probability = get_calibration().probability(self.name, factors)
        chain = [
            {"date": sq.date, "label": "Compressione (squeeze)",
             "detail": "Bollinger dentro Keltner: volatilita compressa"},
            {"date": exp.date, "label": f"Espansione {tone}",
             "detail": "le bande si riaprono: rilascio nel verso del trend"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=strength,
                           strength=strength, probability=probability,
                           signal_date=exp.date, chain=chain, invalidation=None,
                           factors=factors)
