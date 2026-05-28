"""AnalystMomentum (H2): Analyst-Upgrade Momentum hybrid detector.

Hypothesis: when an analyst upgrade is followed within a short window by a
bullish technical confirmation (breakout or ema_cross), the combination
signals above-average post-revision drift.  The academic basis is the
documented "post-revision drift" effect (Womack 1996, Stickel 1995): analyst
upgrades predict abnormal returns, especially when accompanied by price
momentum.

Trigger conditions (bull example):
  - An "analyst_change" event with direction="bull" (upgrade)
  - A same-direction "breakout" OR "ema_cross" event within _CONF_WINDOW_DAYS
    calendar days AFTER the analyst action date

Bear mirror: downgrade + bearish breakout/cross.

Confidence factors:
  - upgrade_present: gate factor (excluded from weighted score) -- the analyst
    action must exist; its magnitude (always 0.5 default) is NOT weighted
    because it is a prerequisite, not a strength indicator.
  - technical_strength: clamped magnitude of the confirming breakout/cross.
    A 4% breakout => clamp(0.04 / 0.04) = 1.0 (full).
"""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, concave, find_after, score_v2
from app.signals.events import Event

# Calendar days after the analyst action to look for technical confirmation.
_CONF_WINDOW_DAYS = 5

# A breakout of this size (fraction of price) is treated as "full" strength.
_BREAKOUT_FULL = 0.04

# Forza anchors for technical_strength. The raw value passed to the curve is
# clamp01(tech_mag / _BREAKOUT_FULL) — ALREADY a 0..1 normalized breakout ratio
# (a 4% breakout => 1.0) — so anchors live in 0..1: raw value at curve-
# contribution 0.45 / 0.75 / 0.88 + saturating ceil.
_TECH_STRENGTH_ANCHORS = (0.3, 0.55, 0.75, 0.9)


class AnalystMomentum:
    name = "analyst_momentum"
    tone = "dynamic"   # resolved per-match from upgrade direction
    sources = [
        "post-revision drift (analyst upgrade momentum)",
        "Womack (1996) analyst revision premium",
        "Stickel (1995) post-recommendation drift",
    ]
    min_bars = 25

    def detect(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext,
    ) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None

        # Find the most recent analyst_change with a clear direction (bull/bear).
        action_evt: Event | None = None
        for e in reversed(events):
            if e.type == "analyst_change" and e.direction in ("bull", "bear"):
                action_evt = e
                break
        if action_evt is None:
            return None

        tone = action_evt.direction  # "bull" or "bear"

        # Look for a same-direction breakout or ema_cross within the window.
        breakout_conf = find_after(
            events, "breakout", after=action_evt.date,
            within_days=_CONF_WINDOW_DAYS, direction=tone,
        )
        ema_conf = find_after(
            events, "ema_cross", after=action_evt.date,
            within_days=_CONF_WINDOW_DAYS, direction=tone,
        )

        # Require at least one technical confirmation.
        if breakout_conf is None and ema_conf is None:
            return None

        # Pick the most informative confirmation (breakout preferred; ema_cross
        # as fallback).
        tech_evt = breakout_conf if breakout_conf is not None else ema_conf
        tech_mag = tech_evt.magnitude or 0.0

        factors = {
            # Gate: the analyst action is a prerequisite, not a strength factor.
            "upgrade_present": 1.0,
            # Weighted: how strong is the confirming technical move?
            "technical_strength": concave(
                clamp01(tech_mag / _BREAKOUT_FULL), _TECH_STRENGTH_ANCHORS),
        }
        weights = {"technical_strength": 1.0}
        # Forza: soft-min over the genuine STRENGTH factor only
        # (technical_strength); upgrade_present is a gate (always 1.0) and is
        # excluded from both the weights and the cap.
        strength = score_v2(factors, weights, strength_keys={"technical_strength"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)

        signal_date = tech_evt.date

        # Build the chain.
        firm = action_evt.payload.get("firm", "analyst")
        to_g = action_evt.payload.get("to_grade", "")
        from_g = action_evt.payload.get("from_grade", "")
        rating_txt = (
            f"{from_g} -> {to_g}" if from_g and to_g
            else (to_g or from_g or "n/d")
        )
        action_label = (
            f"Analyst upgrade: {firm} ({rating_txt})"
            if tone == "bull"
            else f"Analyst downgrade: {firm} ({rating_txt})"
        )
        chain: list[dict] = [
            {
                "date": action_evt.date,
                "label": action_label,
                "detail": (
                    f"Rating change da {firm}: {rating_txt}. "
                    "Atteso post-revision drift."
                ),
                "source": "analyst",
            },
        ]

        if tech_evt.type == "breakout":
            bp = tech_evt.payload.get("level")
            bp_txt = f"{bp:.2f}" if isinstance(bp, (int, float)) else "n/d"
            chain.append({
                "date": tech_evt.date,
                "label": f"Breakout {'rialzista' if tone == 'bull' else 'ribassista'} ({tech_mag * 100:.1f}%)",
                "detail": f"Rottura del livello {bp_txt} dopo l'upgrade dell'analista",
            })
        else:
            f_p = tech_evt.payload.get("fast", "")
            s_p = tech_evt.payload.get("slow", "")
            chain.append({
                "date": tech_evt.date,
                "label": (
                    f"EMA cross {'golden' if tone == 'bull' else 'death'} (EMA{f_p}/EMA{s_p})"
                ),
                "detail": "Incrocio EMA a conferma della revisione dell'analista",
            })

        inv_direction = "ribasso" if tone == "bull" else "rialzo"
        invalidation = {
            "level": float(ctx.last_close * (0.97 if tone == "bull" else 1.03)),
            "reason": (
                f"Chiusura in {inv_direction} del 3% annulla il drift post-upgrade"
            ),
        }

        return SignalMatch(
            name=self.name,
            tone=tone,
            confidence=strength,
            strength=strength,
            probability=probability,
            signal_date=signal_date,
            chain=chain,
            invalidation=invalidation,
            factors=factors,
        )
