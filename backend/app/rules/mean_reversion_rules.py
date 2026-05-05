"""Mean-reversion rules: close N standard deviations away from SMA(period).

The classical statistical-arbitrage / mean-reversion signal:
  - Price extended FAR BELOW its moving average → expect bounce (long)
  - Price extended FAR ABOVE its moving average → expect fade (short)

We measure "extension" as a z-score:

    z = (close - SMA(period)) / stdev(close, period)

Default `period=20` and `threshold_sigma=2.0` — the same parameter
choice that drives Bollinger Bands at 2σ. The two rules are stricter
than RSI-overbought/oversold because they require the actual return
distribution to be in the tail, not just an oscillator reading.
"""
from typing import Any

import pandas as pd


def _z_score(close: pd.Series, period: int) -> tuple[float, float, float] | None:
    """Return (z_score, sma, sigma) at the last bar. None if insufficient bars
    or if sigma is non-positive (constant price → division by zero)."""
    if len(close) < period:
        return None
    window = close.iloc[-period:]
    sma = float(window.mean())
    sigma = float(window.std(ddof=0))  # population std (matches Bollinger 2σ convention)
    if sigma <= 0 or pd.isna(sma):
        return None
    last = float(close.iloc[-1])
    return (last - sma) / sigma, sma, sigma


class MeanReversionLongRule:
    """Close ≥ N σ BELOW SMA(period). Bullish — anticipates bounce."""

    kind = "mean_reversion_long"
    default_params = {"period": 20, "threshold_sigma": 2.0}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        threshold = float(params.get("threshold_sigma", 2.0))
        triple = _z_score(ohlcv["close"], period)
        if triple is None:
            return False
        z, _, _ = triple
        return z <= -threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        threshold = float(params.get("threshold_sigma", 2.0))
        triple = _z_score(ohlcv["close"], period)
        close = float(ohlcv["close"].iloc[-1]) if len(ohlcv) else None
        if triple is None:
            return {"close": close, "sma": None, "sigma": None, "z_score": None,
                    "period": period, "threshold_sigma": threshold}
        z, sma, sigma = triple
        return {
            "close": None if close is None else round(close, 4),
            "sma": round(sma, 4),
            "sigma": round(sigma, 4),
            "z_score": round(z, 3),
            "period": period,
            "threshold_sigma": threshold,
        }


class MeanReversionShortRule:
    """Close ≥ N σ ABOVE SMA(period). Bearish — anticipates fade."""

    kind = "mean_reversion_short"
    default_params = {"period": 20, "threshold_sigma": 2.0}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        threshold = float(params.get("threshold_sigma", 2.0))
        triple = _z_score(ohlcv["close"], period)
        if triple is None:
            return False
        z, _, _ = triple
        return z >= threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        threshold = float(params.get("threshold_sigma", 2.0))
        triple = _z_score(ohlcv["close"], period)
        close = float(ohlcv["close"].iloc[-1]) if len(ohlcv) else None
        if triple is None:
            return {"close": close, "sma": None, "sigma": None, "z_score": None,
                    "period": period, "threshold_sigma": threshold}
        z, sma, sigma = triple
        return {
            "close": None if close is None else round(close, 4),
            "sma": round(sma, 4),
            "sigma": round(sigma, 4),
            "z_score": round(z, 3),
            "period": period,
            "threshold_sigma": threshold,
        }
