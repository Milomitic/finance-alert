"""Gap-and-Go (B11): an opening gap confirmed by a volume spike - the gap is
backed by participation, favouring continuation in the gap direction (vs an
unfilled low-volume gap that tends to fade). Source: gap taxonomy (breakaway
vs exhaustion) + volume confirmation. Confirmed: gap + volume spike."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.calibration_map import get_calibration
from app.signals.detectors.base import SignalMatch, concave, find_after, log_saturate, score_v2
from app.signals.events import Event

_VOL_WINDOW_DAYS = 2
# Forza anchors for gap_size = gap.magnitude (the held opening gap as a fraction
# of the prior close). (a45, a75, a88, ceil): a 2% gap reads modest, a 9% gap is
# the level that genuinely predicts continuation; tail saturates by ~15%.
_GAP_ANCHORS = (0.02, 0.05, 0.09, 0.15)
# Forza ceil for volume_strength: the curve receives (vol/avg - 1.0); ceil=9.0
# maps a 10x-average spike to ~0.85.
_VOL_EXCESS_CEIL = 9.0


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
            # gap_size: gap.magnitude is the held gap as a fraction of prior
            # close → bounded concave curve in those % units.
            "gap_size": concave(gap.magnitude or 0.0, _GAP_ANCHORS),
            # volume_strength: vol_mag == vol/avg (unbounded ratio); pass the
            # EXCESS over average into the log-saturating curve.
            "volume_strength": log_saturate(max(0.0, vol_mag - 1.0), _VOL_EXCESS_CEIL),
            "trend_alignment": 1.0 if trend_aligned else 0.5,
        }
        weights = {"gap_size": 1.0, "volume_strength": 1.0, "trend_alignment": 0.6}
        # Forza: soft-min over the two genuine STRENGTH factors (gap + volume);
        # trend_alignment is a context modulator, excluded from the cap so a
        # mediocre gap can't be laundered to a high score by alignment.
        strength = score_v2(factors, weights,
                            strength_keys={"gap_size", "volume_strength"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        gp = gap.payload.get("gap_pct")
        gp_txt = f"{gp * 100:.1f}%" if isinstance(gp, (int, float)) else "n/d"
        chain = [
            {"date": gap.date, "label": f"Gap {tone}", "detail": f"apertura in gap del {gp_txt}"},
            {"date": gap.date, "label": "Conferma volume",
             "detail": f"{vol_mag:.1f}x la media: gap partecipato"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=strength,
                           strength=strength, probability=probability,
                           signal_date=gap.date, chain=chain, invalidation=None, factors=factors)
