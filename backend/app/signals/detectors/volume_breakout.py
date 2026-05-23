"""Volume-Confirmed Breakout: a Donchian breakout corroborated by a volume
spike within a few bars. Source: Donchian channel breakout + volume
confirmation (Granville OBV lineage)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

_CONFIRM_WINDOW_DAYS = 4


class VolumeBreakout:
    name = "volume_breakout"
    tone = "bull"  # default; emits bull or bear per the breakout direction
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
        # Require a volume spike on/after the breakout, within the window.
        vol = find_after(events, "volume_spike", after=bo.date, within_days=_CONFIRM_WINDOW_DAYS)
        # Also accept a spike ON the breakout bar itself.
        same_bar = any(e.type == "volume_spike" and e.date == bo.date for e in events)
        if vol is None and not same_bar:
            return None
        vol_mag = (vol.magnitude if vol else
                   next((e.magnitude for e in events
                         if e.type == "volume_spike" and e.date == bo.date), None)) or 0.0

        tone = bo.direction or "bull"
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "breakout_strength": clamp01((bo.magnitude or 0.0) / 0.05),   # 5% over level = full
            "volume_strength": clamp01((vol_mag - 1.0) / 2.0),            # 3x avg = full
            "trend_alignment": 1.0 if trend_aligned else 0.4,
        }
        conf = score(factors, {"breakout_strength": 1.0, "volume_strength": 1.2, "trend_alignment": 0.8})
        confirm_date = vol.date if vol else bo.date
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
        return SignalMatch(
            name=self.name, tone=tone, confidence=conf, signal_date=confirm_date,
            chain=chain, invalidation=invalidation, factors=factors,
        )
