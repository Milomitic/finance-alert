"""Geometric chart patterns as STRUCTURE events (confirmed by the ChartPattern
detector via a neckline break). U4a: double bottom (W, bull) / double top (M,
bear). Source: Bulkowski, Encyclopedia of Chart Patterns. Uses the shared
pivot engine."""
from __future__ import annotations

import pandas as pd

from app.signals.events import Event, _iso
from app.signals.pivots import find_pivots

_LEVEL_TOL = 0.04    # two extremes within 4% count as "equal"
_MIN_SEP = 5         # bars between the two extremes
_MAX_SEP = 60
_PIVOT_W = 5


def extract_chart_patterns(ohlcv: pd.DataFrame, *, pivot_w: int = _PIVOT_W) -> list[Event]:
    if len(ohlcv) < 2 * pivot_w + _MIN_SEP + 2:
        return []
    high = ohlcv["high"].astype(float).reset_index(drop=True)
    low = ohlcv["low"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    out: list[Event] = []

    # Double bottom: last two pivot lows ~equal with a pivot high (neckline) between.
    lows = find_pivots(low, pivot_w, kind="low")
    highs = find_pivots(high, pivot_w, kind="high")
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        sep = b - a
        la, lb = low.iloc[a], low.iloc[b]
        if _MIN_SEP <= sep <= _MAX_SEP and la > 0 and abs(lb - la) / la <= _LEVEL_TOL:
            between = [h for h in highs if a < h < b]
            if between:
                neck_i = max(between, key=lambda h: high.iloc[h])
                neckline = float(high.iloc[neck_i])
                out.append(Event(_iso(dates.iloc[b]), "chart_pattern", "bull",
                                 magnitude=float(min(1.0, (neckline - (la + lb) / 2) / neckline))
                                 if neckline else None,
                                 payload={"pattern": "double_bottom", "neckline": neckline,
                                          "lows": [float(la), float(lb)]}))

    # Double top: last two pivot highs ~equal with a pivot low (neckline) between.
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        sep = b - a
        ha, hb = high.iloc[a], high.iloc[b]
        if _MIN_SEP <= sep <= _MAX_SEP and ha > 0 and abs(hb - ha) / ha <= _LEVEL_TOL:
            between = [lo for lo in lows if a < lo < b]
            if between:
                neck_i = min(between, key=lambda lo: low.iloc[lo])
                neckline = float(low.iloc[neck_i])
                out.append(Event(_iso(dates.iloc[b]), "chart_pattern", "bear",
                                 magnitude=float(min(1.0, ((ha + hb) / 2 - neckline) / ((ha + hb) / 2)))
                                 if (ha + hb) else None,
                                 payload={"pattern": "double_top", "neckline": neckline,
                                          "highs": [float(ha), float(hb)]}))
    return out
