"""Bollinger Bands rules: squeeze (low-volatility) and breakout (close outside band)."""
from typing import Any

import pandas as pd

from app.indicators.bb import bb_width, bollinger


class BollingerSqueezeRule:
    kind = "bollinger_squeeze"
    default_params = {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        lookback = int(params.get("lookback", 50))
        percentile = float(params.get("percentile", 0.20))
        widths = bb_width(ohlcv["close"], period=period, k=k)
        recent = widths.iloc[-lookback:].dropna()
        if len(recent) < lookback // 2:
            return False
        last = recent.iloc[-1]
        if pd.isna(last):
            return False
        threshold = recent.quantile(percentile)
        return float(last) < float(threshold)

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        lookback = int(params.get("lookback", 50))
        percentile = float(params.get("percentile", 0.20))
        widths = bb_width(ohlcv["close"], period=period, k=k)
        last = widths.iloc[-1]
        recent = widths.iloc[-lookback:].dropna()
        threshold = float(recent.quantile(percentile)) if len(recent) else None
        return {
            "width": None if pd.isna(last) else round(float(last), 6),
            "threshold": None if threshold is None else round(threshold, 6),
            "period": period,
            "k": k,
            "lookback": lookback,
            "percentile": percentile,
        }


class BollingerBreakoutRule:
    kind = "bollinger_breakout"
    default_params = {"period": 20, "k": 2.0, "direction": "either"}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        direction = str(params.get("direction", "either"))
        upper, _mid, lower = bollinger(ohlcv["close"], period=period, k=k)
        u = upper.iloc[-1]
        l = lower.iloc[-1]
        c = float(ohlcv["close"].iloc[-1])
        if pd.isna(u) or pd.isna(l):
            return False
        if direction == "upper":
            return c > float(u)
        if direction == "lower":
            return c < float(l)
        return c > float(u) or c < float(l)

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        direction = str(params.get("direction", "either"))
        upper, _mid, lower = bollinger(ohlcv["close"], period=period, k=k)
        return {
            "close": round(float(ohlcv["close"].iloc[-1]), 4),
            "upper": None if pd.isna(upper.iloc[-1]) else round(float(upper.iloc[-1]), 4),
            "lower": None if pd.isna(lower.iloc[-1]) else round(float(lower.iloc[-1]), 4),
            "direction": direction,
            "period": period,
            "k": k,
        }
