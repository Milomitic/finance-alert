"""Market-Structure Break (B14), aka BOS / CHoCH: an established swing
structure (higher-highs+higher-lows = uptrend, or LH+LL = downtrend) is
broken when price closes beyond the most recent protected swing - a
change-of-character signalling a possible trend shift. Source: Dow theory /
price-action market structure (swing-based). Confirmed: established structure
(>=2 swings) + the break."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.pivots import find_pivots

_PIVOT_W = 3


class StructureBreak:
    name = "structure_break"
    tone = "bear"
    sources = ["Dow theory / price-action market structure (BOS / CHoCH)"]
    min_bars = 25

    def detect(self, events, ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        high = ohlcv["high"].astype(float).reset_index(drop=True)
        low = ohlcv["low"].astype(float).reset_index(drop=True)
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        last = float(close.iloc[-1])
        hi_piv = find_pivots(high, _PIVOT_W, kind="high")
        lo_piv = find_pivots(low, _PIVOT_W, kind="low")
        if len(hi_piv) < 2 or len(lo_piv) < 2:
            return None
        h1, h2 = high.iloc[hi_piv[-2]], high.iloc[hi_piv[-1]]
        l1, l2 = low.iloc[lo_piv[-2]], low.iloc[lo_piv[-1]]
        uptrend = (h2 > h1) and (l2 > l1)
        downtrend = (h2 < h1) and (l2 < l1)
        if uptrend:
            protected = float(l2)
            broke = last < protected
            tone = "bear"
        elif downtrend:
            protected = float(h2)
            broke = last > protected
            tone = "bull"
        else:
            return None
        if not broke or protected <= 0:
            return None
        magnitude = clamp01(abs(last - protected) / (ctx.atr or (protected * 0.02)) / 3.0) \
            if (ctx.atr or protected) else 0.0
        factors = {
            "break_decisiveness": magnitude,
            "structure": 1.0,
        }
        conf = score(factors, {"break_decisiveness": 1.0})
        last_date = str(ohlcv["date"].iloc[-1])[:10]
        kind_txt = "ribassista (rotto l'ultimo minimo crescente)" if tone == "bear" \
            else "rialzista (rotto l'ultimo massimo decrescente)"
        chain = [
            {"date": last_date, "label": "Struttura di mercato",
             "detail": "sequenza di massimi/minimi che definiva il trend"},
            {"date": last_date, "label": f"Rottura struttura {tone}",
             "detail": f"chiusura {last:.2f} oltre il livello protetto {protected:.2f} - {kind_txt}"},
        ]
        invalidation = {"level": protected,
                        "reason": "ripristino della struttura precedente"}
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors)
