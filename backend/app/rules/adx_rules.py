"""ADX trend-strength rules.

ADX (Average Directional Index) measures the *strength* of a trend regardless
of direction. The +DI / -DI line pair adds the directional read:

  - ADX > 25 with +DI > -DI → strong UP trend (bullish)
  - ADX > 25 with -DI > +DI → strong DOWN trend (bearish)

These are professional desk/trader staples for filtering trending vs
choppy regimes — momentum strategies want ADX above the threshold,
mean-reversion strategies want it below.
"""
from typing import Any

import pandas as pd

from app.indicators.adx import adx


def _last_three(ohlcv: pd.DataFrame, period: int) -> tuple[float, float, float] | None:
    """Compute (adx, +DI, -DI) at the last bar. Returns None when the
    series have insufficient warmup or NaN at the tail."""
    adx_s, plus_di, minus_di = adx(ohlcv, period=period)
    if len(adx_s) == 0 or len(plus_di) == 0 or len(minus_di) == 0:
        return None
    a = adx_s.iloc[-1]
    p = plus_di.iloc[-1]
    m = minus_di.iloc[-1]
    if pd.isna(a) or pd.isna(p) or pd.isna(m):
        return None
    return float(a), float(p), float(m)


class AdxBullishTrendRule:
    """Strong uptrend: ADX above threshold AND +DI > -DI."""

    kind = "adx_bullish_trend"
    default_params = {"period": 14, "threshold": 25.0}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 25.0))
        triple = _last_three(ohlcv, period)
        if triple is None:
            return False
        a, p, m = triple
        return a > threshold and p > m

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 25.0))
        triple = _last_three(ohlcv, period)
        if triple is None:
            return {"adx": None, "plus_di": None, "minus_di": None,
                    "period": period, "threshold": threshold}
        a, p, m = triple
        return {
            "adx": round(a, 2),
            "plus_di": round(p, 2),
            "minus_di": round(m, 2),
            "period": period,
            "threshold": threshold,
        }


class AdxBearishTrendRule:
    """Strong downtrend: ADX above threshold AND -DI > +DI."""

    kind = "adx_bearish_trend"
    default_params = {"period": 14, "threshold": 25.0}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 25.0))
        triple = _last_three(ohlcv, period)
        if triple is None:
            return False
        a, p, m = triple
        return a > threshold and m > p

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 25.0))
        triple = _last_three(ohlcv, period)
        if triple is None:
            return {"adx": None, "plus_di": None, "minus_di": None,
                    "period": period, "threshold": threshold}
        a, p, m = triple
        return {
            "adx": round(a, 2),
            "plus_di": round(p, 2),
            "minus_di": round(m, 2),
            "period": period,
            "threshold": threshold,
        }
