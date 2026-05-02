"""Bollinger Bands: middle = SMA(period), upper/lower = middle ± k*stddev."""
import pandas as pd


def bollinger(
    close: pd.Series, period: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, middle, lower)."""
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + k * std
    lower = middle - k * std
    return upper, middle, lower


def bb_width(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.Series:
    """Width = (upper - lower) / middle. Used for squeeze detection."""
    upper, middle, lower = bollinger(close, period, k)
    return (upper - lower) / middle
