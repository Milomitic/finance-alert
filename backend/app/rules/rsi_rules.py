"""RSI Oversold and RSI Overbought rules."""
from typing import Any

import pandas as pd

from app.indicators.rsi import rsi


class RsiOversoldRule:
    kind = "rsi_oversold"
    default_params = {"period": 14, "threshold": 30}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 30))
        series = rsi(ohlcv["close"], period)
        last = series.iloc[-1]
        if pd.isna(last):
            return False
        return float(last) < threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 30))
        last = rsi(ohlcv["close"], period).iloc[-1]
        return {
            "rsi": None if pd.isna(last) else round(float(last), 2),
            "period": period,
            "threshold": threshold,
        }


class RsiOverboughtRule:
    kind = "rsi_overbought"
    default_params = {"period": 14, "threshold": 70}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 70))
        series = rsi(ohlcv["close"], period)
        last = series.iloc[-1]
        if pd.isna(last):
            return False
        return float(last) > threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 70))
        last = rsi(ohlcv["close"], period).iloc[-1]
        return {
            "rsi": None if pd.isna(last) else round(float(last), 2),
            "period": period,
            "threshold": threshold,
        }
