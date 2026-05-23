# Unified Signals — Phase U2a: structure setups (S/R Flip + Market-Structure Break)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add two distinct, high-value, event-light technical-setup detectors that reuse existing events (no new extractors): Support/Resistance Polarity Flip (B9) and Market-Structure Break / BOS-CHoCH (B14).

**Architecture:** Additive detectors on the proven framework. Both consume events already produced (`sr_level`, `breakout`) and the shared `find_pivots` engine. Each requires ≥2 concatenated elements (structure + break/retest) per the atomic-never-alone rule. Full suite stays green (577 passed / 1 skipped).

**Tech Stack:** Python 3.11, pandas, pytest.

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; ASCII-only; gate-confirmation factors kept in `factors` for display but excluded from `score` weights.

**Scope note:** U2a is the first U2 slice. The new-event setups (B6 MACD divergence, B11 gap-and-go, B13 ADX) are U2b; candlesticks (Layer D) are U2c.

---

### Task 1: Support/Resistance Polarity Flip (B9)

**Files:**
- Create: `backend/app/signals/detectors/sr_flip.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_sr_flip.py`

- [ ] **Step 1: Write the failing test** (event-injection for determinism)
```python
# backend/tests/signals/test_sr_flip.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.sr_flip import SRFlip
from app.signals.events import Event


def _df(closes):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def test_bull_flip_break_then_hold_above_old_resistance():
    # resistance ~100; price breaks to 106, pulls back to 101 (above 100, held).
    closes = [98, 99, 100, 99, 100, 106, 104, 102, 101]
    df = _df([100.0] * 25 + closes)
    events = [Event("2026-02-05", "sr_level", None,
                    payload={"kind": "resistance", "level": 100.0})]
    m = SRFlip().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("flip" in s["label"].lower() or "polarit" in s["label"].lower()
               or "supporto" in s["label"].lower() for s in m.chain)


def test_silent_when_price_back_below_level():
    closes = [98, 99, 100, 106, 104, 99]   # broke then fell back BELOW 100
    df = _df([100.0] * 25 + closes)
    events = [Event("2026-02-05", "sr_level", None,
                    payload={"kind": "resistance", "level": 100.0})]
    assert SRFlip().detect(events, df, build_context(df)) is None


def test_silent_without_sr_level():
    df = _df([100.0] * 30)
    assert SRFlip().detect([], df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/sr_flip.py
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

_BREAK_MARGIN = 0.01   # close must clear the level by >=1% to count as a break
_RETEST_PCT = 0.025    # pullback must come back within 2.5% of the level


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
        # Try a bullish flip on the most recent resistance, else a bearish flip
        # on the most recent support.
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
                "break": 1.0,   # gate (display only)
                "hold": 1.0,    # gate (display only)
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
            return SignalMatch(name=self.name, tone=tone, confidence=conf,
                               signal_date=last_date, chain=chain,
                               invalidation=invalidation, factors=factors)
        return None
```
Append to `registry.py`:
```python
from app.signals.detectors.sr_flip import SRFlip
# ... append SRFlip() to DETECTORS
```

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_sr_flip.py tests/signals/ -q` → green.
```bash
git add backend/app/signals/detectors/sr_flip.py backend/app/signals/detectors/registry.py backend/tests/signals/test_sr_flip.py
git commit -m "feat(signals): Support/Resistance Polarity Flip detector (B9)"
```

---

### Task 2: Market-Structure Break / BOS-CHoCH (B14)

**Files:**
- Create: `backend/app/signals/detectors/structure_break.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_structure_break.py`

- [ ] **Step 1: Write the failing test**
```python
# backend/tests/signals/test_structure_break.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.structure_break import StructureBreak


def _df(closes):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1.0, "low": c - 1.0, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def _uptrend_then_break_down():
    # rising swings (HH/HL) then a decisive break below the last higher-low.
    seq = []
    base = 100.0
    for k in range(4):                       # 4 up-legs making HH + HL
        for d in (0, 3, 6, 3):               # up, up, peak, pullback (the HL)
            seq.append(base + k * 6 + d)
    seq += [seq[-1] - 12]                     # break well below the last HL
    return _df(seq)


def test_bear_choch_breaks_last_higher_low():
    df = _uptrend_then_break_down()
    m = StructureBreak().detect([], df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bear" and m.confidence > 0
    assert any("struttura" in s["label"].lower() for s in m.chain)


def test_silent_on_intact_uptrend():
    df = _df([100 + i for i in range(40)])    # clean uptrend, no break
    assert StructureBreak().detect([], df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/structure_break.py
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
            protected = float(l2)                       # most recent higher-low
            broke = last < protected
            tone = "bear"
        elif downtrend:
            protected = float(h2)                       # most recent lower-high
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
            "structure": 1.0,   # gate (display only)
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
```
Append to `registry.py`:
```python
from app.signals.detectors.structure_break import StructureBreak
# ... append StructureBreak() to DETECTORS
```

- [ ] **Step 4: Run + full suite + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_structure_break.py tests/signals/ -q` → green, then full suite `tests/ -q`.
```bash
git add backend/app/signals/detectors/structure_break.py backend/app/signals/detectors/registry.py backend/tests/signals/test_structure_break.py
git commit -m "feat(signals): Market-Structure Break (BOS/CHoCH) detector (B14)"
```

---

## Self-review notes
- Both detectors reuse existing events/engine (no new extractor): SRFlip uses `sr_level` + close; StructureBreak uses `find_pivots`. ✓
- Atomic-never-alone: SRFlip = break + retest + hold; StructureBreak = established structure (>=2 swings) + the break. Gate factors excluded from score weights. ✓
- Distinct from existing detectors: SRFlip (polarity flip) and StructureBreak (BOS) don't overlap volume_breakout / trend_pullback / oversold_reversal. ✓
- Type consistency: `SignalMatch`, `clamp01`, `score`, `find_pivots`, `SignalContext.atr` used consistently; both append to `DETECTORS`. ✓
- ASCII-only (accent-free Italian: "polarita", "struttura"). ✓

## Follow-up (rest of U2)
- **U2b** — new-event setups: B6 MACD divergence (+ `macd_divergence` extractor), B11 gap-and-go (+ `gap` extractor), B13 ADX confirmation (+ `adx_trend` extractor), B7 hidden divergence (extend rsi divergence).
- **U2c** — candlesticks (Layer D): candle-shape events + confirmed candlestick detectors.
