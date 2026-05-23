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
_HNS_TOL = 0.05      # shoulders within 5% count as "equal"
_TRI_TOL = 0.02      # flat side of triangle within 2%


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
    # Inverse H&S (bull): last 3 pivot lows, head lowest, shoulders ~equal.
    if len(lows) >= 3:
        s1, head, s2 = lows[-3], lows[-2], lows[-1]
        l1, lh, l2 = low.iloc[s1], low.iloc[head], low.iloc[s2]
        if lh < l1 and lh < l2 and l1 > 0 and abs(l2 - l1) / l1 <= _HNS_TOL \
                and (s2 - s1) <= _MAX_SEP:
            necks = [high.iloc[h] for h in highs if s1 < h < s2]
            if necks:
                neckline = float(max(necks))
                out.append(Event(_iso(dates.iloc[s2]), "chart_pattern", "bull",
                                 magnitude=float(min(1.0, (neckline - lh) / neckline)) if neckline else None,
                                 payload={"pattern": "inverse_head_shoulders", "neckline": neckline,
                                          "head": float(lh)}))
    # H&S top (bear): last 3 pivot highs, head highest, shoulders ~equal.
    if len(highs) >= 3:
        s1, head, s2 = highs[-3], highs[-2], highs[-1]
        h1, hh, h2 = high.iloc[s1], high.iloc[head], high.iloc[s2]
        if hh > h1 and hh > h2 and h1 > 0 and abs(h2 - h1) / h1 <= _HNS_TOL \
                and (s2 - s1) <= _MAX_SEP:
            necks = [low.iloc[lo] for lo in lows if s1 < lo < s2]
            if necks:
                neckline = float(min(necks))
                out.append(Event(_iso(dates.iloc[s2]), "chart_pattern", "bear",
                                 magnitude=float(min(1.0, (hh - neckline) / hh)) if hh else None,
                                 payload={"pattern": "head_shoulders", "neckline": neckline,
                                          "head": float(hh)}))
    # Ascending triangle (bull): flat highs + rising lows.
    if len(highs) >= 3 and len(lows) >= 3:
        h = [high.iloc[i] for i in highs[-3:]]
        lo3 = [low.iloc[i] for i in lows[-3:]]
        flat_highs = max(h) > 0 and (max(h) - min(h)) / max(h) <= _TRI_TOL
        rising_lows = lo3[0] < lo3[1] < lo3[2]
        if flat_highs and rising_lows:
            neckline = float(sum(h) / len(h))
            out.append(Event(_iso(dates.iloc[lows[-1]]), "chart_pattern", "bull",
                             magnitude=0.6,
                             payload={"pattern": "ascending_triangle", "neckline": neckline}))
        # Descending triangle (bear): flat lows + falling highs.
        flat_lows = min(lo3) > 0 and (max(lo3) - min(lo3)) / min(lo3) <= _TRI_TOL
        falling_highs = h[0] > h[1] > h[2]
        if flat_lows and falling_highs:
            neckline = float(sum(lo3) / len(lo3))
            out.append(Event(_iso(dates.iloc[highs[-1]]), "chart_pattern", "bear",
                             magnitude=0.6,
                             payload={"pattern": "descending_triangle", "neckline": neckline}))
    # Symmetrical triangle: converging (falling highs + rising lows); direction
    # resolved by which boundary price breaks. neckline = the broken pivot.
    if len(highs) >= 3 and len(lows) >= 3:
        h3 = [high.iloc[i] for i in highs[-3:]]
        l3 = [low.iloc[i] for i in lows[-3:]]
        converging = (h3[0] > h3[1] > h3[2]) and (l3[0] < l3[1] < l3[2])
        if converging:
            last_close = float(ohlcv["close"].astype(float).iloc[-1])
            recent_high = float(h3[-1])
            recent_low = float(l3[-1])
            if last_close > recent_high:
                out.append(Event(_iso(dates.iloc[-1]), "chart_pattern", "bull",
                                 magnitude=0.55,
                                 payload={"pattern": "symmetrical_triangle", "neckline": recent_high}))
            elif last_close < recent_low:
                out.append(Event(_iso(dates.iloc[-1]), "chart_pattern", "bear",
                                 magnitude=0.55,
                                 payload={"pattern": "symmetrical_triangle", "neckline": recent_low}))
    return out
