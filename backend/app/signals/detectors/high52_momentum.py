"""52-Week-High Momentum: price at/near its 52-week high within an uptrend - a
documented momentum anomaly. Source: George & Hwang, "The 52-Week High and
Momentum Investing" (J. Finance 2004). Computes proximity directly (no event)."""
from __future__ import annotations

import pandas as pd

from app.core.config import settings
from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import (
    SignalMatch,
    clamp01,
    concave,
    score_v2,
    trend_maturity_factor,
)
from app.signals.events import Event

_WINDOW = 252
_NEAR_THRESHOLD = 0.97
# Forza: proximity is the raw price/52w-high ratio (last / hi_52), which lives
# in ~[0.97, 1.0] once the detector's _NEAR_THRESHOLD gate has passed. Anchors
# live in that ratio unit: at the 52w high (~0.999) the momentum anomaly is
# strongest (-> 0.88); merely 0.985 of the high sits at the low anchor (0.45).
_PROXIMITY_ANCHORS = (0.985, 0.995, 0.999, 1.0)


class High52Momentum:
    name = "high52_momentum"
    tone = "bull"
    sources = ['George & Hwang, "The 52-Week High and Momentum Investing" (J. Finance 2004)']
    min_bars = 60

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        high = ohlcv["high"].astype(float)
        low = ohlcv["low"].astype(float)
        window = min(_WINDOW, len(ohlcv))
        hi_52 = float(high.iloc[-window:].max())
        lo_52 = float(low.iloc[-window:].min())
        last = ctx.last_close
        if hi_52 <= 0:
            return None
        proximity = last / hi_52
        if proximity < _NEAR_THRESHOLD or ctx.trend_sign <= 0:
            return None
        # Confirmation (atomic-never-alone): the momentum must be corroborated
        # by a fresh breakout or a volume spike, not bare proximity.
        confirmed = any(e.type in ("breakout", "volume_spike") for e in events)
        if not confirmed:
            return None
        rng = hi_52 - lo_52
        momentum = clamp01((last - lo_52) / rng) if rng > 0 else 0.0
        factors = {
            "proximity": concave(proximity, _PROXIMITY_ANCHORS),
            "trend": 1.0 if ctx.trend_sign > 0 else 0.0,
            "momentum": momentum,
            "confirmation": 1.0,
            "trend_maturity": trend_maturity_factor(ctx.trend_age),
        }
        # `momentum` is empirically saturated / uninformative for this anomaly,
        # so it is kept in `factors` for display but DROPPED from the weights.
        # `trend` and `confirmation` are gate conditions - kept in `factors` as
        # displayed evidence but excluded from score weights to avoid inflating
        # the floor.
        weights = {"proximity": 1.0,
                   "trend_maturity": settings.signal_trend_maturity_weight}
        # Forza: soft-min over the single STRENGTH factor (proximity); momentum
        # (saturated, dropped) and trend_maturity (a context modulator) are
        # excluded from strength_keys so a mediocre proximity can't be laundered.
        strength = score_v2(factors, weights, strength_keys={"proximity"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        last_date = str(ohlcv["date"].iloc[-1])[:10]
        chain = [
            {"date": last_date, "label": "Vicino al massimo 52 settimane",
             "detail": f"prezzo a {proximity * 100:.1f}% del massimo a 52w"},
            {"date": last_date, "label": "Trend rialzista",
             "detail": "EMA lunga in salita: momentum confermato"},
            {"date": last_date, "label": "Conferma breakout/volume",
             "detail": "momentum corroborato da rottura o spike di volume"},
        ]
        invalidation = {"level": lo_52, "reason": "rottura del minimo a 52 settimane"}
        return SignalMatch(name=self.name, tone="bull",
                           strength=strength, probability=probability,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors,
                           annotations={"levels": [{"label": "Max 52 settimane",
                                                    "price": hi_52,
                                                    "kind": "resistance"}],
                                        "points": []})
