"""Oversold/Overbought Reversal at Support/Resistance: an RSI extreme that
coincides with price sitting at a confirmed S/R level, with the last bar
turning back in the reversal direction. Source: Wilder (1978) RSI extremes;
Murphy - buy near support / sell near resistance. Confirmed (never a bare
RSI reading): requires the S/R-proximity + a turn."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_NEAR_PCT = 0.03   # within 3% of the level counts as "at" the level


class OversoldReversal:
    name = "oversold_reversal"
    tone = "bull"
    sources = ['Wilder (1978) RSI extremes; Murphy - buy support / sell resistance']
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        extremes = [e for e in events if e.type == "rsi_extreme"]
        if not extremes:
            return None
        ext = extremes[-1]
        tone = ext.direction or "bull"
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        open_ = ohlcv["open"].astype(float).reset_index(drop=True) if "open" in ohlcv.columns else close
        last = float(close.iloc[-1])
        last_open = float(open_.iloc[-1])
        want = "support" if tone == "bull" else "resistance"
        levels = [e.payload.get("level") for e in events
                  if e.type == "sr_level" and e.payload.get("kind") == want
                  and isinstance(e.payload.get("level"), (int, float))]
        near = any(abs(last - lv) / lv <= _NEAR_PCT for lv in levels if lv) if levels else False
        if not near:
            return None
        # "Turning" bar: for a bull reversal the last bar must close >= its open
        # (neutral doji at support counts — price tested the level and held).
        turned = (last >= last_open) if tone == "bull" else (last <= last_open)
        if not turned:
            return None
        rsi_v = ext.payload.get("rsi")
        if tone == "bull" and isinstance(rsi_v, (int, float)):
            extremity = clamp01((30.0 - rsi_v) / 25.0)
        elif isinstance(rsi_v, (int, float)):
            extremity = clamp01((rsi_v - 70.0) / 25.0)
        else:
            extremity = 0.0
        factors = {
            "rsi_extremity": extremity,
            "at_level": 1.0,   # gate, kept for display
            "turn": 1.0,       # gate, kept for display
        }
        conf = score(factors, {"rsi_extremity": 1.0})
        nearest = min((lv for lv in levels if lv), key=lambda lv: abs(last - lv))
        chain = [
            {"date": ext.date, "label": f"RSI {'ipervenduto' if tone == 'bull' else 'ipercomprato'}",
             "detail": f"RSI {rsi_v}"},
            {"date": _last_date(ohlcv), "label": f"Reversal a {'supporto' if tone == 'bull' else 'resistenza'}",
             "detail": f"prezzo {last:.2f} al livello {nearest:.2f}, barra che gira"},
        ]
        invalidation = {"level": float(nearest),
                        "reason": f"rottura del {'supporto' if tone == 'bull' else 'resistenza'}"}
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=_last_date(ohlcv), chain=chain,
                           invalidation=invalidation, factors=factors)


def _last_date(ohlcv: pd.DataFrame) -> str:
    return str(ohlcv["date"].iloc[-1])[:10]
