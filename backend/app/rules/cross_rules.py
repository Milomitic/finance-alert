"""Golden Cross and Death Cross rules (EMA fast vs EMA slow).

May 2026: switched from SMA to EMA — see commit history for the
catalog-wide moving-average swap. The rule `kind` strings stay
`golden_cross` / `death_cross` so existing alert rows in DB remain
queryable; only the underlying math + the snapshot field names changed
(`fast_ma` / `slow_ma` replaces `fast_sma` / `slow_sma`).
"""
from typing import Any

import pandas as pd

from app.indicators.ema import ema


def _both_emas(close: pd.Series, fast: int, slow: int) -> tuple[pd.Series, pd.Series]:
    return ema(close, fast), ema(close, slow)


class GoldenCrossRule:
    kind = "golden_cross"
    default_params = {"fast": 50, "slow": 200}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        ema_f, ema_s = _both_emas(ohlcv["close"], fast, slow)
        # Need last 2 bars of both EMAs to detect crossing.
        # EMA has no warmup NaN (it initialises to the first value), so
        # the isna() guard is defensive — fires only on empty inputs.
        if len(ema_f) < 2 or ema_f.iloc[-2:].isna().any() or ema_s.iloc[-2:].isna().any():
            return False
        return bool(ema_f.iloc[-2] <= ema_s.iloc[-2] and ema_f.iloc[-1] > ema_s.iloc[-1])

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        ema_f, ema_s = _both_emas(ohlcv["close"], fast, slow)
        last_f = ema_f.iloc[-1]
        last_s = ema_s.iloc[-1]
        return {
            "fast_ma": None if pd.isna(last_f) else round(float(last_f), 4),
            "slow_ma": None if pd.isna(last_s) else round(float(last_s), 4),
            "fast_period": fast,
            "slow_period": slow,
        }


class DeathCrossRule:
    kind = "death_cross"
    default_params = {"fast": 50, "slow": 200}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        ema_f, ema_s = _both_emas(ohlcv["close"], fast, slow)
        if len(ema_f) < 2 or ema_f.iloc[-2:].isna().any() or ema_s.iloc[-2:].isna().any():
            return False
        return bool(ema_f.iloc[-2] >= ema_s.iloc[-2] and ema_f.iloc[-1] < ema_s.iloc[-1])

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        ema_f, ema_s = _both_emas(ohlcv["close"], fast, slow)
        last_f = ema_f.iloc[-1]
        last_s = ema_s.iloc[-1]
        return {
            "fast_ma": None if pd.isna(last_f) else round(float(last_f), 4),
            "slow_ma": None if pd.isna(last_s) else round(float(last_s), 4),
            "fast_period": fast,
            "slow_period": slow,
        }
