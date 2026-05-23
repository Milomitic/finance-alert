"""Support/Resistance Polarity Flip (B9): a broken level reverses role and is
retested (old resistance becomes support and holds -> bull continuation;
old support becomes resistance -> bear). Source: Murphy - "after a resistance
peak is broken it usually provides support on subsequent pullbacks". Confirmed:
requires the break + a successful retest-hold (>=2 events)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_BREAK_MARGIN = 0.01
_RETEST_PCT = 0.025


class SRFlip:
    name = "sr_flip"
    tone = "bull"
    sources = ['Murphy - broken resistance becomes support (polarity flip)']
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        last = float(close.iloc[-1])
        for kind in ("resistance", "support"):
            levels = [e.payload.get("level") for e in events
                      if e.type == "sr_level" and e.payload.get("kind") == kind
                      and isinstance(e.payload.get("level"), (int, float))]
            if not levels:
                continue
            level = levels[-1]
            if not level:
                continue
            if kind == "resistance":
                broke = bool((close > level * (1 + _BREAK_MARGIN)).any())
                retested = abs(last - level) / level <= _RETEST_PCT or last > level
                held = last > level
                tone = "bull"
            else:
                broke = bool((close < level * (1 - _BREAK_MARGIN)).any())
                retested = abs(last - level) / level <= _RETEST_PCT or last < level
                held = last < level
                tone = "bear"
            if not (broke and retested and held):
                continue
            proximity = clamp01(1.0 - abs(last - level) / (level * _RETEST_PCT)) if level else 0.0
            trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
            factors = {
                "retest_proximity": proximity,
                "trend_alignment": 1.0 if trend_aligned else 0.5,
                "break": 1.0,
                "hold": 1.0,
            }
            conf = score(factors, {"retest_proximity": 1.0, "trend_alignment": 0.8})
            last_date = str(ohlcv["date"].iloc[-1])[:10]
            new_role = "supporto" if tone == "bull" else "resistenza"
            chain = [
                {"date": last_date, "label": f"Rottura {kind}",
                 "detail": f"prezzo ha rotto il livello {level:.2f}"},
                {"date": last_date, "label": f"Flip di polarita ({new_role})",
                 "detail": f"retest del livello {level:.2f} come nuovo {new_role}, tenuta"},
            ]
            invalidation = {"level": float(level),
                            "reason": f"ritorno oltre il livello {level:.2f} (flip fallito)"}
            level_kind = "support" if tone == "bull" else "resistance"
            level_label = "Supporto (ex resistenza)" if tone == "bull" else "Resistenza (ex supporto)"
            return SignalMatch(name=self.name, tone=tone, confidence=conf,
                               signal_date=last_date, chain=chain,
                               invalidation=invalidation, factors=factors,
                               annotations={"levels": [{"label": level_label,
                                                        "price": float(level),
                                                        "kind": level_kind}],
                                            "points": []})
        return None
