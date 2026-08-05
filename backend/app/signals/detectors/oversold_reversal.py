"""Oversold/Overbought Reversal at Support/Resistance: an RSI extreme that
coincides with price sitting at a confirmed S/R level, with the last bar
turning back in the reversal direction. Source: Wilder (1978) RSI extremes;
Murphy - buy near support / sell near resistance. Confirmed (never a bare
RSI reading): requires the S/R-proximity + a turn."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, concave, score_v2
from app.signals.events import Event
from app.signals.setups.base import SetupMatch, distance_to_trigger_atr

_NEAR_PCT = 0.03   # within 3% of the level counts as "at" the level
# Setup-only: how far out we still consider the level "in play". Wider than
# _NEAR_PCT because the point of a setup is to see it COMING — at 3% the move
# is often already under way, which is the problem setups exist to solve.
_APPROACH_PCT = 0.08
# Forza: rsi_extremity is already a normalized [0, 1] distance past the 30/70
# threshold (clamp01((30-rsi)/25) for bull). Anchors live in that 0..1 unit.
# A deep oversold RSI≈10 -> extremity 0.80 = the empirically-strong reading
# (-> 0.88); a mild extremity 0.30 (RSI≈22.5) sits at the low anchor (-> 0.45).
_RSI_EXTREMITY_ANCHORS = (0.3, 0.55, 0.8, 1.0)


class OversoldReversal:
    name = "oversold_reversal"
    tone = "bull"
    sources = ['Wilder (1978) RSI extremes; Murphy - buy support / sell resistance']
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        extremes = [e for e in events if e.type == "rsi_extreme"]
        if not extremes:
            return None
        ext = extremes[-1]
        tone = ext.direction or "bull"
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        open_ = ohlcv["open"].astype(float).reset_index(drop=True) if "open" in ohlcv.columns else close
        last = float(close.iloc[-1])
        last_open = float(open_.iloc[-1])
        want = "support" if tone == "bull" else "resistance"
        levels = [e.payload.get("level") for e in events
                  if e.type == "sr_level" and e.payload.get("kind") == want
                  and isinstance(e.payload.get("level"), (int, float))]
        near = any(abs(last - lv) / lv <= _NEAR_PCT for lv in levels if lv) if levels else False
        if not near:
            return None
        # "Turning" bar: for a bull reversal the last bar must close >= its open
        # (neutral doji at support counts — price tested the level and held).
        turned = (last >= last_open) if tone == "bull" else (last <= last_open)
        if not turned:
            return None
        rsi_v = ext.payload.get("rsi")
        if tone == "bull" and isinstance(rsi_v, (int, float)):
            extremity = clamp01((30.0 - rsi_v) / 25.0)
        elif isinstance(rsi_v, (int, float)):
            extremity = clamp01((rsi_v - 70.0) / 25.0)
        else:
            extremity = 0.0
        factors = {
            "rsi_extremity": concave(extremity, _RSI_EXTREMITY_ANCHORS),
            "at_level": 1.0,   # gate, kept for display
            "turn": 1.0,       # gate, kept for display
        }
        weights = {"rsi_extremity": 1.0}
        # Forza: soft-min over the single STRENGTH factor (rsi_extremity);
        # at_level + turn are gates (always 1.0), excluded from the weights so
        # they can't inflate the floor.
        strength = score_v2(factors, weights, strength_keys={"rsi_extremity"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        nearest = min((lv for lv in levels if lv), key=lambda lv: abs(last - lv))
        chain = [
            {"date": ext.date, "label": f"RSI {'ipervenduto' if tone == 'bull' else 'ipercomprato'}",
             "detail": f"RSI {rsi_v}"},
            {"date": _last_date(ohlcv), "label": f"Reversal a {'supporto' if tone == 'bull' else 'resistenza'}",
             "detail": f"prezzo {last:.2f} al livello {nearest:.2f}, barra che gira"},
        ]
        invalidation = {"level": float(nearest),
                        "reason": f"rottura del {'supporto' if tone == 'bull' else 'resistenza'}"}
        level_kind = "support" if tone == "bull" else "resistance"
        level_label = "Supporto" if tone == "bull" else "Resistenza"
        return SignalMatch(name=self.name, tone=tone,
                           strength=strength, probability=probability,
                           signal_date=_last_date(ohlcv), chain=chain,
                           invalidation=invalidation, factors=factors,
                           annotations={"levels": [{"label": level_label,
                                                    "price": float(nearest),
                                                    "kind": level_kind}],
                                        "points": []})


    # ── Setup (pre-trigger) ─────────────────────────────────────────────
    # ADDITIVE: `detect` above is untouched, so fired signals and the outcome
    # warehouse are unaffected. This only surfaces the state `detect` discards.
    #
    # The gate chain is: RSI extreme → at a level → the bar turned. The last
    # gate is the trigger and it fires once the move is already under way; the
    # two before it can hold for days. That interval is the lead time.
    def proximity(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext
    ) -> SetupMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        extremes = [e for e in events if e.type == "rsi_extreme"]
        if not extremes:
            return None          # gate 1 unmet: nothing is forming yet
        ext = extremes[-1]
        tone = ext.direction or "bull"
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        open_ = ohlcv["open"].astype(float).reset_index(drop=True) if "open" in ohlcv.columns else close
        last = float(close.iloc[-1])
        last_open = float(open_.iloc[-1])

        want = "support" if tone == "bull" else "resistance"
        levels = [e.payload.get("level") for e in events
                  if e.type == "sr_level" and e.payload.get("kind") == want
                  and isinstance(e.payload.get("level"), (int, float))]
        levels = [lv for lv in levels if lv]
        if not levels:
            return None
        nearest = min(levels, key=lambda lv: abs(last - lv))
        dist = abs(last - nearest) / nearest

        # Already turned AND at the level → detect() fired; not a setup.
        turned = (last >= last_open) if tone == "bull" else (last <= last_open)
        if dist <= _NEAR_PCT and turned:
            return None
        # Too far for the level to be in play at all.
        if dist > _APPROACH_PCT:
            return None

        rsi_v = ext.payload.get("rsi")
        if tone == "bull" and isinstance(rsi_v, (int, float)):
            extremity = clamp01((30.0 - rsi_v) / 25.0)
        elif isinstance(rsi_v, (int, float)):
            extremity = clamp01((rsi_v - 70.0) / 25.0)
        else:
            extremity = 0.0

        at_level = dist <= _NEAR_PCT
        if at_level:
            # Two of three gates held; only the turn is outstanding. This is
            # the highest-value state: one bar away, and the level gives an
            # invalidation to plan against.
            prox = 0.85
            missing = (
                f"la barra deve girare (chiudere {'sopra' if tone == 'bull' else 'sotto'} "
                f"la sua apertura) al livello {nearest:.2f}"
            )
        else:
            # Approaching: needs to reach the level AND turn. Proximity decays
            # with distance so the ordering favours what is closest to playing out.
            prox = 0.35 + 0.30 * (1.0 - (dist - _NEAR_PCT) / (_APPROACH_PCT - _NEAR_PCT))
            missing = (
                f"il prezzo deve raggiungere il livello {nearest:.2f} "
                f"({dist * 100:.1f}% di distanza) e girare"
            )

        level_label = "Supporto" if tone == "bull" else "Resistenza"
        return SetupMatch(
            detector=self.name,
            tone=tone,
            proximity=round(prox, 3),
            distance_atr=distance_to_trigger_atr(
                ctx.last_close, float(nearest), ctx.atr
            ),
            missing=missing,
            factors={
                "rsi_extremity": concave(extremity, _RSI_EXTREMITY_ANCHORS),
                "level_distance": clamp01(1.0 - dist / _APPROACH_PCT),
                "gate_rsi_extreme": 1.0,
            },
            annotations={"levels": [{"label": level_label, "price": float(nearest),
                                     "kind": want}], "points": []},
        )


def _last_date(ohlcv: pd.DataFrame) -> str:
    return str(ohlcv["date"].iloc[-1])[:10]
