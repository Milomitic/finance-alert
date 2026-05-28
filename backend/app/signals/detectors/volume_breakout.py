"""Volume-Confirmed Breakout: a Donchian breakout corroborated by a volume
spike within a few bars. Source: Donchian channel breakout + volume
confirmation (Granville OBV lineage)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.core.config import settings
from app.signals.calibration_map import get_calibration
from app.signals.detectors.base import (
    SignalMatch, concave, find_after, log_saturate, score_v2, trend_maturity_factor,
)
from app.signals.events import Event

# How many calendar days after a breakout a volume spike may still confirm it.
_CONFIRM_WINDOW_DAYS = 4
_TREND_MISALIGN_FLOOR = 0.4   # a signal against the prevailing trend keeps this much credit
# Forza anchors for breakout_strength = (close-level)/level, i.e. the % a bar
# closed above the broken Donchian high. (a45, a75, a88, ceil) in those raw %
# units: 1.5% over the level reads as a modest break, 8% as the level that
# genuinely predicts continuation; the tail saturates by ~15%.
_BREAKOUT_ANCHORS = (0.015, 0.04, 0.08, 0.15)
# Forza ceil for volume_strength: the curve receives (vol/avg - 1.0) (excess
# over the average), so ceil=9.0 means a 10x-average spike maps to ~0.85.
_VOL_EXCESS_CEIL = 9.0
_FACTOR_WEIGHTS = {
    "breakout_strength": 1.0,
    "volume_strength": 1.2,
    "trend_alignment": 0.8,
}


class VolumeBreakout:
    name = "volume_breakout"
    # Protocol default / metadata; the emitted tone follows the breakout direction.
    tone = "bull"
    sources = ["Donchian channel breakout + volume confirmation (OBV lineage)"]
    min_bars = 21  # minimum for a 20-bar lookback + the breakout bar itself

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        # Most-recent breakout event.
        breakouts = [e for e in events if e.type == "breakout"]
        if not breakouts:
            return None
        bo = breakouts[-1]
        # Confirmation = a volume spike that corroborates the breakout. `find_after`
        # is STRICTLY after bo.date, so it catches spikes on the FOLLOWING bars; a
        # spike landing ON the breakout bar is matched separately. Both branches are
        # needed; neither is dead code. A later spike (if any) wins over a same-bar
        # one, preserving the original "vol if vol else same-bar" precedence.
        later_spike = find_after(events, "volume_spike", after=bo.date, within_days=_CONFIRM_WINDOW_DAYS)
        same_bar_spike = next(
            (e for e in events if e.type == "volume_spike" and e.date == bo.date), None
        )
        confirming = later_spike or same_bar_spike
        if confirming is None:
            return None
        vol_mag = confirming.magnitude or 0.0

        tone = bo.direction or "bull"
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        # NOTE: extract_volume_spike only emits when volume >= 2x its average, so
        # vol_mag is >= 2.0 by construction and volume_strength starts partway up
        # its curve rather than at 0.
        factors = {
            # breakout_strength: bo.magnitude == (close-level)/level (% over the
            # broken high) → bounded concave curve in those % units.
            "breakout_strength": concave(bo.magnitude or 0.0, _BREAKOUT_ANCHORS),
            # volume_strength: vol_mag == vol/avg (unbounded ratio); pass the
            # EXCESS over average (vol_mag-1.0) into the log-saturating curve.
            "volume_strength": log_saturate(max(0.0, vol_mag - 1.0), _VOL_EXCESS_CEIL),
            "trend_alignment": 1.0 if trend_aligned else _TREND_MISALIGN_FLOOR,
            "trend_maturity": trend_maturity_factor(ctx.trend_age),
        }
        weights = {**_FACTOR_WEIGHTS,
                   "trend_maturity": settings.signal_trend_maturity_weight}
        # Forza: soft-min over the two genuine STRENGTH factors (breakout +
        # volume); trend_alignment and trend_maturity are context modulators,
        # excluded from the cap so a mediocre break can't be laundered to a high
        # score by alignment/maturity riding over it.
        strength = score_v2(factors, weights,
                            strength_keys={"breakout_strength", "volume_strength"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        confirm_date = confirming.date
        chain = [
            {"date": bo.date, "label": f"Breakout {tone}",
             "detail": f"chiusura oltre il livello {bo.payload.get('level')}"},
            {"date": confirm_date, "label": "Conferma volume",
             "detail": f"{vol_mag:.1f}x la media a 20 sedute"},
        ]
        invalidation = (
            {"level": float(bo.payload.get("level")),
             "reason": "rientro sotto il livello di breakout"}
            if bo.payload.get("level") is not None else None
        )
        bo_level = bo.payload.get("level")
        primary_levels = (
            [{"label": "Breakout", "price": float(bo_level), "kind": "breakout"}]
            if isinstance(bo_level, (int, float)) else []
        )
        return SignalMatch(
            name=self.name, tone=tone,
            strength=strength, probability=probability, signal_date=confirm_date,
            chain=chain, invalidation=invalidation, factors=factors,
            annotations={"levels": primary_levels, "points": []},
        )
