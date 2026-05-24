"""Volume-Confirmed Breakout: a Donchian breakout corroborated by a volume
spike within a few bars. Source: Donchian channel breakout + volume
confirmation (Granville OBV lineage)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.core.config import settings
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score, trend_maturity_factor
from app.signals.events import Event

# How many calendar days after a breakout a volume spike may still confirm it.
_CONFIRM_WINDOW_DAYS = 4
# Confidence reference points. Each factor is normalised to [0,1] then weighted.
_BREAKOUT_REF_PCT = 0.05      # a close this fraction above the broken level => full
_VOL_EXCESS_REF = 2.0         # volume this many x ABOVE its average (i.e. 3x avg) => full
_TREND_MISALIGN_FLOOR = 0.4   # a signal against the prevailing trend keeps this much credit
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
        # vol_mag is >= 2.0 by construction and volume_strength effectively spans
        # [0.5, 1.0] rather than the full [0, 1].
        factors = {
            "breakout_strength": clamp01((bo.magnitude or 0.0) / _BREAKOUT_REF_PCT),
            "volume_strength": clamp01((vol_mag - 1.0) / _VOL_EXCESS_REF),
            "trend_alignment": 1.0 if trend_aligned else _TREND_MISALIGN_FLOOR,
            "trend_maturity": trend_maturity_factor(ctx.trend_age),
        }
        conf = score(factors, {**_FACTOR_WEIGHTS,
                               "trend_maturity": settings.signal_trend_maturity_weight})
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
            name=self.name, tone=tone, confidence=conf, signal_date=confirm_date,
            chain=chain, invalidation=invalidation, factors=factors,
            annotations={"levels": primary_levels, "points": []},
        )
