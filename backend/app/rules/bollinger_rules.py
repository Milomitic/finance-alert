"""Bollinger Bands rule: breakout (close outside band).

The squeeze sibling was retired (Alembic migration
`47c2035665bd_drop_bollinger_squeeze_rules`) — it produced too many
false positives in choppy regimes and overlapped with mean-reversion
rules that have a cleaner signal-to-noise ratio.
"""
from typing import Any

import pandas as pd

from app.indicators.bb import bollinger


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
