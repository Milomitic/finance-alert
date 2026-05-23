"""Confirmed swing-pivot detection shared across detectors (divergence, S/R,
geometric patterns). A bar is a pivot only if it has `width` neighbours on
each side that it dominates - so the most recent confirmable pivot lags by
`width` bars (intrinsic to confirmation, not a bug)."""
from __future__ import annotations

import pandas as pd


def find_pivots(series: pd.Series, width: int, *, kind: str) -> list[int]:
    """Indices of confirmed local extrema: a pivot low (kind='low') is the
    minimum of the [i-width, i+width] window (mirror for 'high'). Only bars
    with `width` neighbours on each side qualify."""
    idx: list[int] = []
    n = len(series)
    for i in range(width, n - width):
        window = series.iloc[i - width:i + width + 1]
        v = series.iloc[i]
        if kind == "low" and v == window.min():
            idx.append(i)
        elif kind == "high" and v == window.max():
            idx.append(i)
    return idx
