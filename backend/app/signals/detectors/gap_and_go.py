"""Gap-and-Go (B11): an opening gap confirmed by a volume spike - the gap is
backed by participation, favouring continuation in the gap direction (vs an
unfilled low-volume gap that tends to fade). Source: gap taxonomy (breakaway
vs exhaustion) + volume confirmation. Confirmed: gap + volume spike."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, find_after, score, soft01
from app.signals.events import Event

_VOL_WINDOW_DAYS = 2


class GapAndGo:
    name = "gap_and_go"
    tone = "bull"
    sources = ["Gap taxonomy (breakaway vs exhaustion) + volume confirmation"]
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        gaps = [e for e in events if e.type == "gap"]
        if not gaps:
            return None
        gap = gaps[-1]
        tone = gap.direction or "bull"
        # Confirmation: a volume spike on the gap bar or just after.
        vol_same = any(e.type == "volume_spike" and e.date == gap.date for e in events)
        vol_after = find_after(events, "volume_spike", after=gap.date, within_days=_VOL_WINDOW_DAYS)
        if not (vol_same or vol_after):
            return None
        vol_mag = next((e.magnitude for e in events
                        if e.type == "volume_spike" and e.date == gap.date), None) \
            or (vol_after.magnitude if vol_after else None) or 0.0
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "gap_size": soft01(gap.magnitude or 0.0, 0.05),     # 5% gap = strong
            "volume_strength": soft01(vol_mag - 1.0, 2.0),      # 3x avg = strong
            "trend_alignment": 1.0 if trend_aligned else 0.5,
        }
        conf = score(factors, {"gap_size": 1.0, "volume_strength": 1.0, "trend_alignment": 0.6})
        gp = gap.payload.get("gap_pct")
        gp_txt = f"{gp * 100:.1f}%" if isinstance(gp, (int, float)) else "n/d"
        chain = [
            {"date": gap.date, "label": f"Gap {tone}", "detail": f"apertura in gap del {gp_txt}"},
            {"date": gap.date, "label": "Conferma volume",
             "detail": f"{vol_mag:.1f}x la media: gap partecipato"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=gap.date, chain=chain, invalidation=None, factors=factors)
