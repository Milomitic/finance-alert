"""Shared fixture builders for market_stats_service tests."""
from datetime import date, timedelta

import pandas as pd


def build_ohlcv(n_bars: int, start_close: float = 100.0, drift: float = 0.1) -> pd.DataFrame:
    """Deterministic OHLCV DataFrame: linear close drift, fixed volume.

    Used to assert metric correctness with predictable values.
    """
    rows = []
    today = date(2026, 5, 1)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        close = start_close + drift * i
        rows.append({
            "date": d,
            "open": close - 0.5,
            "high": close + 0.5,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000,
        })
    return pd.DataFrame(rows)


def build_ohlcv_volume_spike(n_bars: int = 30) -> pd.DataFrame:
    """Same as build_ohlcv but the last bar has 5× volume."""
    df = build_ohlcv(n_bars)
    df.loc[df.index[-1], "volume"] = 5_000_000
    return df
