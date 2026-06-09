"""Trend-Pullback Continuation: after a moving-average golden/death cross, price
pulls back toward the fast MA and then resumes in the trend direction. Source:
Brock, Lakonishok & LeBaron (J. Finance 1992) on MA-crossover rules; pullback
entry as the consolidated refinement."""
from __future__ import annotations

import pandas as pd

from app.indicators.ema import ema
from app.signals.context import SignalContext
from app.core.config import settings
from app.signals.calibration_map import get_calibration
from app.signals.detectors.base import SignalMatch, concave, score_v2, trend_maturity_factor
from app.signals.events import Event

_FAST = 50
_SLOW = 200
# Pullback "touch" tolerance around the fast EMA. Floor (1.5%) preserved; in a
# high-vol name we LOOSEN it to k·ATR/EMA so a genuine test isn't missed, and in
# a low-vol name the floor still applies. ATR-relative tracks the regime instead
# of a fixed % (spec Phase 2c).
_PULLBACK_TOL = 0.015
_PULLBACK_ATR_K = 0.5
# Forza anchors for the EMA50/EMA200 spread (|spread|/close): raw value at
# curve-contribution 0.45 / 0.75 / 0.88 + saturating ceil. Distribution-
# grounded (p50≈6%, p90≈14%, p99≈30%); a 30%+ spread = a decisively strong
# trend. So a merely-ordinary 6% pullback no longer reads as near-max strength.
_TREND_STRENGTH_ANCHORS = (0.05, 0.14, 0.30, 0.60)


class TrendPullback:
    name = "trend_pullback"
    tone = "bull"
    sources = ["Brock, Lakonishok & LeBaron (J. Finance 1992) - MA crossover rules + pullback"]
    min_bars = _SLOW + 10

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        crosses = [e for e in events if e.type == "ema_cross"]
        if not crosses:
            return None
        cross = crosses[-1]
        tone = cross.direction or "bull"
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        ef = ema(close, _FAST).reset_index(drop=True)
        es = ema(close, _SLOW).reset_index(drop=True)
        last = len(close) - 1
        fast_now = ef.iloc[last]
        if pd.isna(fast_now) or fast_now == 0:
            return None
        recent = range(max(0, last - 20), last + 1)
        # ATR-relative touch tolerance, floored at the legacy 1.5% so it only
        # ever LOOSENS for high-vol names (never tightens below the floor).
        tol = _PULLBACK_TOL
        if ctx.atr and fast_now:
            tol = max(_PULLBACK_TOL, (ctx.atr * _PULLBACK_ATR_K) / fast_now)
        if tone == "bull":
            tagged = any(close.iloc[i] <= ef.iloc[i] * (1 + tol) for i in recent)
            resumed = close.iloc[last] > fast_now
        else:
            tagged = any(close.iloc[i] >= ef.iloc[i] * (1 - tol) for i in recent)
            resumed = close.iloc[last] < fast_now
        if not (tagged and resumed):
            return None

        spread = abs(ef.iloc[last] - es.iloc[last]) / close.iloc[last]
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "trend_strength": concave(spread, _TREND_STRENGTH_ANCHORS),
            "trend_alignment": 1.0 if trend_aligned else 0.4,
            "resume": 1.0 if resumed else 0.0,
            "trend_maturity": trend_maturity_factor(ctx.trend_age),
        }
        # `resume` is a gate condition (detect returns None when it is false),
        # so it is always 1.0 here - kept in `factors` as displayed evidence
        # but excluded from the score weights to avoid inflating the floor.
        weights = {"trend_strength": 1.0, "trend_alignment": 1.0,
                   "trend_maturity": settings.signal_trend_maturity_weight}
        # Forza: soft-min over the genuine STRENGTH factor only (trend_strength)
        # — alignment + maturity are context modulators, excluded from the cap so
        # a mediocre trend can't be laundered to a high score by being aligned.
        strength = score_v2(factors, weights, strength_keys={"trend_strength"})
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)
        chain = [
            {"date": cross.date, "label": f"Incrocio EMA {tone}",
             "detail": f"EMA{_FAST}/EMA{_SLOW} ({'golden' if tone == 'bull' else 'death'} cross)"},
            {"date": _last_date(ohlcv), "label": "Pullback + ripresa",
             "detail": f"ritorno verso EMA{_FAST} e ripartenza nel verso del trend"},
        ]
        invalidation = {"level": float(es.iloc[last]),
                        "reason": f"chiusura oltre EMA{_SLOW} contro il trend"}
        return SignalMatch(name=self.name, tone=tone,
                           strength=strength, probability=probability,
                           signal_date=_last_date(ohlcv), chain=chain,
                           invalidation=invalidation, factors=factors)


def _last_date(ohlcv: pd.DataFrame) -> str:
    return str(ohlcv["date"].iloc[-1])[:10]
