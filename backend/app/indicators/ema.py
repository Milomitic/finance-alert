"""Exponential Moving Average (alpha = 2/(period+1), adjust=False)."""
import pandas as pd


def ema(close: pd.Series, period: int) -> pd.Series:
    """Compute EMA. Initializes to the first value (no warmup NaN)."""
    return close.ewm(span=period, adjust=False).mean()
