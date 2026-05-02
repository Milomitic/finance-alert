"""Breakout rule: today's close breaks above prior `period` close max."""
from typing import Any

import pandas as pd


class BreakoutRule:
    kind = "breakout"
    default_params = {"period": 20}

    def _prior_max(self, ohlcv: pd.DataFrame, period: int) -> float | None:
        if len(ohlcv) < period + 1:
            return None
        return float(ohlcv["close"].iloc[-(period + 1):-1].max())

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        prior_max = self._prior_max(ohlcv, period)
        if prior_max is None:
            return False
        return float(ohlcv["close"].iloc[-1]) > prior_max

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        prior_max = self._prior_max(ohlcv, period)
        close = float(ohlcv["close"].iloc[-1])
        return {
            "close": round(close, 4),
            "prior_max": None if prior_max is None else round(prior_max, 4),
            "period": period,
        }
