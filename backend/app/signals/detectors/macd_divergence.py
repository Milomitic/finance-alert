# backend/app/signals/detectors/macd_divergence.py
"""MACD Regular Divergence (B6): price makes a lower low while the MACD line
makes a higher low (bull) or mirror (bear) - a momentum-reversal setup.
Source: Appel (MACD); divergence as the consolidated momentum-reversal read.
Consumes the macd_divergence event."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, concave, score_v2
from app.signals.events import Event

_COUNTER_TREND = 1.0
_WITH_TREND = 0.5
# Forza anchors for divergence_amplitude. `d.magnitude` is ALREADY a 0..1
# normalized amplitude (clamp01(d.magnitude)), so anchors live in 0..1:
# raw value at curve-contribution 0.45 / 0.75 / 0.88 + saturating ceil.
_AMPLITUDE_ANCHORS = (0.30, 0.55, 0.75, 0.90)


class MacdDivergence:
    name = "macd_divergence"
    tone = "bull"
    sources = ["Appel MACD; regular divergence as a momentum-reversal read"]
    min_bars = 35

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        divs = [e for e in events if e.type == "macd_divergence"]
        if not divs:
            return None
        d = divs[-1]
        tone = d.direction or "bull"
        counter = (tone == "bull" and ctx.trend_sign <= 0) or (tone == "bear" and ctx.trend_sign >= 0)
        factors = {
            "divergence_amplitude": concave(d.magnitude or 0.0, _AMPLITUDE_ANCHORS),
            "trend_context": _COUNTER_TREND if counter else _WITH_TREND,
        }
        weights = {"divergence_amplitude": 1.0, "trend_context": 1.0}
        # Forza: soft-min over the genuine STRENGTH factor only
        # (divergence_amplitude); trend_context is a context modulator, excluded
        # from the cap so a mediocre divergence can't be laundered to a high
        # score by being counter-trend.
        strength = score_v2(factors, weights, strength_keys={"divergence_amplitude"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        pivots = d.payload.get("pivot_dates") or [d.date, d.date]
        chain = [
            {"date": pivots[0], "label": "Primo estremo di prezzo", "detail": "minimo/massimo iniziale"},
            {"date": d.date, "label": f"Divergenza MACD {tone}",
             "detail": "prezzo e linea MACD divergono (setup di inversione)"},
        ]
        close_by_date = {str(row.date)[:10]: float(row.close)
                         for row in ohlcv.itertuples(index=False)}
        points = [{"date": dt, "price": close_by_date[dt]}
                  for dt in pivots if dt in close_by_date]
        return SignalMatch(name=self.name, tone=tone,
                           strength=strength, probability=probability,
                           signal_date=d.date, chain=chain, invalidation=None, factors=factors,
                           annotations={"levels": [], "points": points})
