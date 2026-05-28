# backend/app/signals/detectors/candle_reversal.py
"""Candlestick Reversal (Layer D): a reliable reversal candle (engulfing,
hammer/shooting-star, morning/evening star) that forms AT a support/resistance
level - confirmed price-action reversal. Source: Nison - candlestick reliability
rises sharply at S/R with context. Confirmed: candle + at-level (never a bare
candle)."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, concave, score_v2
from app.signals.events import Event

_NEAR_PCT = 0.03
# Forza: candle_strength is the candle body/range ratio, already in [0, 1].
# Anchors live in that 0..1 unit. A near-marubozu engulfing (~0.96 body/range)
# is the empirically-strong reading -> 0.88; an ordinary 0.8 body sits mid-band.
_CANDLE_STRENGTH_ANCHORS = (0.75, 0.90, 0.96, 0.99)

_PATTERN_IT = {
    "hammer": "Hammer", "shooting_star": "Shooting star",
    "engulfing": "Engulfing", "morning_star": "Morning star",
    "evening_star": "Evening star",
}


class CandleReversal:
    name = "candle_reversal"
    tone = "bull"
    sources = ["Nison - candlestick reversals confirmed at support/resistance"]
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        candles = [e for e in events if e.type == "candle_reversal"]
        if not candles:
            return None
        cdl = candles[-1]
        tone = cdl.direction or "bull"
        last = ctx.last_close
        want = "support" if tone == "bull" else "resistance"
        levels = [e.payload.get("level") for e in events
                  if e.type == "sr_level" and e.payload.get("kind") == want
                  and isinstance(e.payload.get("level"), (int, float))]
        near = any(abs(last - lv) / lv <= _NEAR_PCT for lv in levels if lv) if levels else False
        if not near:
            return None
        pattern = cdl.payload.get("pattern", "candle")
        factors = {
            "candle_strength": concave(cdl.magnitude or 0.0, _CANDLE_STRENGTH_ANCHORS),
            "at_level": 1.0,   # gate (display only)
        }
        weights = {"candle_strength": 1.0}
        # Forza: soft-min over the single STRENGTH factor (candle_strength);
        # at_level is a gate (always 1.0), excluded so it can't inflate the floor.
        strength = score_v2(factors, weights, strength_keys={"candle_strength"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        nearest = min((lv for lv in levels if lv), key=lambda lv: abs(last - lv))
        loc = "supporto" if tone == "bull" else "resistenza"
        chain = [
            {"date": cdl.date, "label": f"Candela di inversione {tone}",
             "detail": f"pattern {_PATTERN_IT.get(pattern, pattern)}"},
            {"date": cdl.date, "label": f"A {loc}",
             "detail": f"prezzo {last:.2f} al livello {nearest:.2f}"},
        ]
        invalidation = {"level": float(nearest), "reason": f"rottura del {loc}"}
        level_kind = "support" if tone == "bull" else "resistance"
        level_label = "Supporto" if tone == "bull" else "Resistenza"
        return SignalMatch(name=self.name, tone=tone, confidence=strength,
                           strength=strength, probability=probability,
                           signal_date=cdl.date, chain=chain,
                           invalidation=invalidation, factors=factors,
                           annotations={"levels": [{"label": level_label,
                                                    "price": float(nearest),
                                                    "kind": level_kind}],
                                        "points": []})
