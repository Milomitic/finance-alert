"""MACD bullish/bearish cross rules."""
from typing import Any

import pandas as pd

from app.indicators.macd import macd

_DEFAULT_LOOKBACK = 10


def _snapshot(ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    signal = int(params.get("signal", 9))
    line, sig, hist = macd(ohlcv["close"], fast=fast, slow=slow, signal=signal)
    last_line = line.iloc[-1]
    last_sig = sig.iloc[-1]
    last_hist = hist.iloc[-1]
    return {
        "line": None if pd.isna(last_line) else round(float(last_line), 4),
        "signal": None if pd.isna(last_sig) else round(float(last_sig), 4),
        "hist": None if pd.isna(last_hist) else round(float(last_hist), 4),
        "fast": fast,
        "slow": slow,
        "signal_period": signal,
    }


class MacdBullishCrossRule:
    kind = "macd_bullish_cross"
    default_params = {"fast": 12, "slow": 26, "signal": 9}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        lookback = int(params.get("lookback", _DEFAULT_LOOKBACK))
        _line, _sig, hist = macd(ohlcv["close"], fast=fast, slow=slow, signal=signal)
        recent = hist.iloc[-lookback:]
        for i in range(1, len(recent)):
            if recent.iloc[i - 1] <= 0 and recent.iloc[i] > 0:
                return True
        return False

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        return _snapshot(ohlcv, params)


class MacdBearishCrossRule:
    kind = "macd_bearish_cross"
    default_params = {"fast": 12, "slow": 26, "signal": 9}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        lookback = int(params.get("lookback", _DEFAULT_LOOKBACK))
        _line, _sig, hist = macd(ohlcv["close"], fast=fast, slow=slow, signal=signal)
        recent = hist.iloc[-lookback:]
        for i in range(1, len(recent)):
            if recent.iloc[i - 1] >= 0 and recent.iloc[i] < 0:
                return True
        return False

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        return _snapshot(ohlcv, params)
