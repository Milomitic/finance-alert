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
from app.signals.detectors.base import SignalMatch, clamp01, concave, score_v2
from app.signals.events import Event
from app.signals.setups.base import SetupMatch

_NEAR_PCT = 0.03
# ── Setup-only thresholds ────────────────────────────────────────────────
# TIGHTER than the trigger's 3%, not wider. "Within 3% of some support"
# describes a large slice of the universe at any moment, and emitting on it
# would recreate the 1214-setups flood. At 1.5% price is genuinely testing
# the level rather than merely in its neighbourhood.
_SETUP_NEAR_PCT = 0.015
# A pivot becomes a LEVEL by being respected more than once. One touch is the
# swing that defined it; the interesting case is price coming back to it.
# This is also the only factor here that actually ranks — proximity is
# near-binary per state, so without it the list could not be ordered.
_MIN_TOUCHES = 2
_TOUCH_TOL = 0.02
_TOUCH_ANCHORS = (2.0, 3.0, 5.0, 8.0)
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
        return SignalMatch(name=self.name, tone=tone,
                           strength=strength, probability=probability,
                           signal_date=cdl.date, chain=chain,
                           invalidation=invalidation, factors=factors,
                           annotations={"levels": [{"label": level_label,
                                                    "price": float(nearest),
                                                    "kind": level_kind}],
                                        "points": []})

    # ── Setup (pre-trigger) ─────────────────────────────────────────────
    # Gates: a reversal candle exists → it is at an S/R level. The candle IS
    # the trigger, so the pre-trigger state is "price is testing a proven
    # level and the reversal candle has not printed yet" — the user's
    # "rimbalzo su livelli tecnici importanti", seen while it is still a wait.
    #
    # Deliberately STRICTER than detect(): see _SETUP_NEAR_PCT/_MIN_TOUCHES.
    # A setup that fires on a condition most of the market satisfies is not a
    # watchlist, and this detector's gate ("near a level") is exactly that.
    def proximity(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext
    ) -> SetupMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        # A candle already printed at a level → detect() fired; not a setup.
        if [e for e in events if e.type == "candle_reversal"]:
            return None

        last = ctx.last_close
        tone = "bull" if ctx.trend_sign >= 0 else "bear"
        want = "support" if tone == "bull" else "resistance"
        levels = [e.payload.get("level") for e in events
                  if e.type == "sr_level" and e.payload.get("kind") == want
                  and isinstance(e.payload.get("level"), (int, float))]
        levels = [lv for lv in levels if lv]
        if not levels:
            return None

        nearest = min(levels, key=lambda lv: abs(last - lv))
        dist = abs(last - nearest) / nearest
        if dist > _SETUP_NEAR_PCT:
            return None

        # How often price has actually come back to this level. The sr_level
        # event carries no strength, so it is counted here from the bars: a
        # level respected repeatedly is a level, a single pivot is noise.
        # EXCLUDING the current bar: price is at the level right now — that is
        # the setup condition, not evidence the level has been respected
        # before. Counting it inflated every level by one, so a lone pivot
        # cleared the minimum and the filter did nothing.
        probe = (ohlcv["low"] if tone == "bull" else ohlcv["high"]).iloc[:-1]
        touches = int((abs(probe.astype(float) - nearest) / nearest <= _TOUCH_TOL).sum())
        if touches < _MIN_TOUCHES:
            return None

        level_label = "Supporto" if tone == "bull" else "Resistenza"
        return SetupMatch(
            detector=self.name,
            tone=tone,
            # One gate of two holds, and the outstanding one is a single
            # candle — near-term, but genuinely unresolved: price at a level
            # can break it instead of bouncing.
            proximity=0.70,
            missing=(
                f"manca la candela di inversione al {level_label.lower()} "
                f"{nearest:.2f} (testato {touches} volte)"
            ),
            factors={
                "level_strength": concave(float(touches), _TOUCH_ANCHORS),
                "level_distance": clamp01(1.0 - dist / _SETUP_NEAR_PCT),
                "gate_at_level": 1.0,
            },
            annotations={"levels": [{"label": level_label, "price": float(nearest),
                                     "kind": want}], "points": []},
        )
