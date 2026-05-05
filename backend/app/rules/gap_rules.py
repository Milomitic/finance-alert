"""Gap rules: today's open vs yesterday's close.

A gap is the discontinuity between the prior session's close and the
current session's open — driven by overnight news / earnings / catalysts.
Day-trader desks treat sizable gaps as actionable signals:

  - GapUp ≥ N% → bullish catalyst (positive news, beat earnings)
  - GapDown ≥ N% → bearish catalyst (negative news, missed earnings)

We use the (open - prev_close) / prev_close fraction. Default threshold
is 2% (0.02) which filters noise while catching the gaps a desk would
flag for the morning meeting.
"""
from typing import Any

import pandas as pd


def _gap_pct(ohlcv: pd.DataFrame) -> float | None:
    """Today's open / yesterday's close − 1, or None when insufficient bars."""
    if len(ohlcv) < 2:
        return None
    prev_close = float(ohlcv["close"].iloc[-2])
    today_open = float(ohlcv["open"].iloc[-1])
    if prev_close <= 0:
        return None
    return (today_open / prev_close) - 1.0


class GapUpRule:
    kind = "gap_up"
    default_params = {"threshold_pct": 0.02}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        threshold = float(params.get("threshold_pct", 0.02))
        gap = _gap_pct(ohlcv)
        return gap is not None and gap >= threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        threshold = float(params.get("threshold_pct", 0.02))
        gap = _gap_pct(ohlcv)
        prev_close = float(ohlcv["close"].iloc[-2]) if len(ohlcv) >= 2 else None
        today_open = float(ohlcv["open"].iloc[-1]) if len(ohlcv) >= 1 else None
        return {
            "gap_pct": None if gap is None else round(gap, 4),
            "prev_close": None if prev_close is None else round(prev_close, 4),
            "open": None if today_open is None else round(today_open, 4),
            "threshold_pct": threshold,
        }


class GapDownRule:
    kind = "gap_down"
    default_params = {"threshold_pct": 0.02}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        threshold = float(params.get("threshold_pct", 0.02))
        gap = _gap_pct(ohlcv)
        # gap_pct is negative when price gapped down; compare to -threshold.
        return gap is not None and gap <= -threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        threshold = float(params.get("threshold_pct", 0.02))
        gap = _gap_pct(ohlcv)
        prev_close = float(ohlcv["close"].iloc[-2]) if len(ohlcv) >= 2 else None
        today_open = float(ohlcv["open"].iloc[-1]) if len(ohlcv) >= 1 else None
        return {
            "gap_pct": None if gap is None else round(gap, 4),
            "prev_close": None if prev_close is None else round(prev_close, 4),
            "open": None if today_open is None else round(today_open, 4),
            "threshold_pct": threshold,
        }
