"""ADX Trend Confirmation (B13): a strong directional regime (ADX high with
+DI/-DI alignment) confirmed by a breakout in the same direction - a
trend-following entry with a strength filter. Source: Wilder (1978) ADX/DMI.
Confirmed: adx_trend + breakout."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, concave, find_after, score_v2
from app.signals.events import Event

_BREAK_WINDOW_DAYS = 4
# Forza anchors. adx_strength is the adx_trend magnitude = (ADX-25)/75 (already
# 0..1), so anchors live in those NORMALISED units: ADX35→0.133 maps to ~0.75,
# ADX50→0.333 maps to ~0.88 — a merely-sufficient ADX(25) no longer reads strong.
_ADX_STRENGTH_ANCHORS = (0.05, 0.13, 0.33, 0.6)
# di_spread receives the RAW |+DI - -DI| (DI points); a 35-point spread = a
# decisively one-sided directional regime → ~0.88.
_DI_SPREAD_ANCHORS = (12.0, 22.0, 35.0, 50.0)


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
        di_spread_raw = abs((a.payload.get("plus_di") or 0) - (a.payload.get("minus_di") or 0))
        factors = {
            "adx_strength": concave(clamp01(a.magnitude or 0.0), _ADX_STRENGTH_ANCHORS),
            "di_spread": concave(di_spread_raw, _DI_SPREAD_ANCHORS),
            "breakout": 1.0,   # gate (display only)
        }
        weights = {"adx_strength": 1.0, "di_spread": 0.6}
        # Forza: soft-min over the two STRENGTH factors (adx_strength + di_spread)
        # — the always-1.0 breakout gate is excluded so a weak trend can't be
        # laundered to a high score by the confirmation gate alone.
        strength = score_v2(factors, weights,
                            strength_keys={"adx_strength", "di_spread"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        adx_v = a.payload.get("adx")
        chain = [
            {"date": a.date, "label": f"Trend forte (ADX) {tone}",
             "detail": f"ADX {adx_v} con DI allineati"},
            {"date": a.date, "label": "Conferma breakout",
             "detail": "rottura nel verso del trend"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=strength,
                           strength=strength, probability=probability,
                           signal_date=a.date, chain=chain, invalidation=None, factors=factors)
