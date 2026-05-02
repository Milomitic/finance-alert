"""Volume-based rules: VolumeSpikeRule."""
from typing import Any

import pandas as pd


class VolumeSpikeRule:
    kind = "volume_spike"
    default_params = {"window": 20, "threshold": 2.0}

    def _ratio(self, ohlcv: pd.DataFrame, window: int) -> float | None:
        if len(ohlcv) < window + 1:
            return None
        prior = ohlcv["volume"].iloc[-(window + 1):-1]
        avg = float(prior.mean())
        if avg <= 0:
            return None
        today = float(ohlcv["volume"].iloc[-1])
        return today / avg

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        window = int(params.get("window", 20))
        threshold = float(params.get("threshold", 2.0))
        r = self._ratio(ohlcv, window)
        return r is not None and r > threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        window = int(params.get("window", 20))
        threshold = float(params.get("threshold", 2.0))
        r = self._ratio(ohlcv, window)
        return {
            "ratio": None if r is None else round(r, 3),
            "window": window,
            "threshold": threshold,
        }
