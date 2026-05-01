"""Golden Cross and Death Cross rules (SMA fast vs SMA slow)."""
from typing import Any

import pandas as pd

from app.indicators.sma import sma


def _both_smas(close: pd.Series, fast: int, slow: int) -> tuple[pd.Series, pd.Series]:
    return sma(close, fast), sma(close, slow)


class GoldenCrossRule:
    kind = "golden_cross"
    default_params = {"fast": 50, "slow": 200}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        sma_f, sma_s = _both_smas(ohlcv["close"], fast, slow)
        # Need last 2 bars of both SMAs to detect crossing
        if len(sma_f) < 2 or sma_f.iloc[-2:].isna().any() or sma_s.iloc[-2:].isna().any():
            return False
        return bool(sma_f.iloc[-2] <= sma_s.iloc[-2] and sma_f.iloc[-1] > sma_s.iloc[-1])

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        sma_f, sma_s = _both_smas(ohlcv["close"], fast, slow)
        last_f = sma_f.iloc[-1]
        last_s = sma_s.iloc[-1]
        return {
            "fast_sma": None if pd.isna(last_f) else round(float(last_f), 4),
            "slow_sma": None if pd.isna(last_s) else round(float(last_s), 4),
            "fast_period": fast,
            "slow_period": slow,
        }


class DeathCrossRule:
    kind = "death_cross"
    default_params = {"fast": 50, "slow": 200}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        sma_f, sma_s = _both_smas(ohlcv["close"], fast, slow)
        if len(sma_f) < 2 or sma_f.iloc[-2:].isna().any() or sma_s.iloc[-2:].isna().any():
            return False
        return bool(sma_f.iloc[-2] >= sma_s.iloc[-2] and sma_f.iloc[-1] < sma_s.iloc[-1])

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        sma_f, sma_s = _both_smas(ohlcv["close"], fast, slow)
        last_f = sma_f.iloc[-1]
        last_s = sma_s.iloc[-1]
        return {
            "fast_sma": None if pd.isna(last_f) else round(float(last_f), 4),
            "slow_sma": None if pd.isna(last_s) else round(float(last_s), 4),
            "fast_period": fast,
            "slow_period": slow,
        }
