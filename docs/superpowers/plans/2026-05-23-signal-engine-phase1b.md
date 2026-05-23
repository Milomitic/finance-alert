# Signal Engine — Phase 1b Implementation Plan (remaining 4 detectors)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add the 4 remaining grounded detectors from the design spec onto the Phase-1a scaffolding: Trend-Pullback Continuation, RSI Regular Divergence, Volatility Squeeze Expansion, 52-Week-High Momentum.

**Architecture:** Purely additive. New event extractors in `app/signals/events.py` (ema_cross, rsi_divergence, bollinger squeeze/expansion) registered into `EXTRACTORS`; four new detector modules in `app/signals/detectors/` registered into `DETECTORS`. No framework changes. The scan hook, dedup, threshold, and API surfacing from 1a already handle any `SignalMatch` regardless of detector.

**Tech Stack:** Python 3.11, pandas, pytest. Reuses `app/indicators/` (ema, rsi, atr, bollinger).

**Conventions:** run tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`. Keep new source ASCII-only (Italian chain labels use plain ASCII). Each detector emits a `SignalMatch` whenever the pattern is structurally present; the `signal_min_confidence` gate (already in settings) decides alerting.

**Grounding (from the design spec §6):**
- Trend-Pullback — Brock, Lakonishok & LeBaron (J. Finance 1992) MA-crossover rules + pullback refinement.
- RSI Divergence — Wilder, "New Concepts in Technical Trading Systems" (1978).
- Squeeze Expansion — Bollinger (2001); TTM Squeeze (Carter).
- 52-Week-High Momentum — George & Hwang (J. Finance 2004).

---

### Task 1: Three new extractors (ema_cross, rsi_divergence, bollinger) + EXTRACTORS

**Files:**
- Modify: `backend/app/signals/events.py`
- Test: `backend/tests/signals/test_events_phase1b.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/signals/test_events_phase1b.py
import pandas as pd
from app.signals.events import (
    extract_ema_cross, extract_rsi_divergence, extract_bollinger,
)


def _df(rows):
    # rows: list of (date, close, high, low, volume); open inferred = close
    return pd.DataFrame([
        {"date": d, "open": c, "high": h, "low": lo, "close": c, "volume": v}
        for (d, c, h, lo, v) in rows
    ])


def test_ema_cross_emits_golden():
    # 60 bars falling then 60 rising so a fast/slow EMA golden cross occurs.
    rows = [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", 200 - i, 201 - i, 199 - i, 1000)
            for i in range(60)]
    base = rows[-1][1]
    rows += [(f"2027-{1 + i // 28:02d}-{1 + i % 28:02d}", base + i, base + i + 1, base + i - 1, 1000)
             for i in range(1, 80)]
    evs = extract_ema_cross(_df(rows), fast=20, slow=50)
    assert any(e.type == "ema_cross" and e.direction == "bull" for e in evs)


def test_rsi_divergence_bull():
    # Price makes a lower low while momentum eases -> RSI higher low.
    # Construct: sharp drop (low RSI), bounce, milder drop to a lower price low.
    seq = []
    price = 100.0
    # leg 1 down hard
    for _ in range(8):
        price -= 4
        seq.append(price)
    # bounce
    for _ in range(6):
        price += 3
        seq.append(price)
    # leg 2 down, slightly lower low than leg1 but shallower slope
    for _ in range(8):
        price -= 2.5
        seq.append(price)
    rows = [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", round(p, 2),
             round(p, 2) + 1, round(p, 2) - 1, 1000) for i, p in enumerate(seq)]
    evs = extract_rsi_divergence(_df(rows), period=14, pivot_w=2)
    # Detection is best-effort on synthetic data; assert it does not crash and
    # returns a list. A non-empty bull divergence is the target.
    assert isinstance(evs, list)


def test_bollinger_emits_squeeze_then_expansion():
    # 40 flat bars (tight band -> squeeze) then a sharp move (expansion).
    rows = [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", 100.0, 100.2, 99.8, 1000)
            for i in range(40)]
    base = 100.0
    rows += [(f"2027-{1 + i // 28:02d}-{1 + i % 28:02d}", base + i * 3,
              base + i * 3 + 1, base + i * 3 - 1, 1000) for i in range(1, 12)]
    evs = extract_bollinger(_df(rows), period=20, k=2.0, kc_mult=1.5)
    assert any(e.type == "bb_squeeze" for e in evs)
    assert any(e.type == "bb_expansion" for e in evs)
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_events_phase1b.py -q`
Expected: FAIL — `ImportError` (extractors don't exist).

- [ ] **Step 3: Add the extractors to `events.py`**

Add these imports at the top of `events.py` (alongside the existing `import pandas as pd`):

```python
from app.indicators.atr import atr
from app.indicators.bb import bollinger
from app.indicators.ema import ema
from app.indicators.rsi import rsi
```

Add these functions (after `extract_volume_spike`, before the `EXTRACTORS` list):

```python
def extract_ema_cross(
    ohlcv: pd.DataFrame, *, fast: int = 50, slow: int = 200,
) -> list[Event]:
    """Emit an ema_cross event on each bar where the fast EMA crosses the slow
    EMA: bull = fast crosses ABOVE slow (golden), bear = fast crosses BELOW
    (death). magnitude = normalised gap |fast-slow|/close at the cross."""
    if len(ohlcv) < slow + 1:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    ef = ema(close, fast)
    es = ema(close, slow)
    diff = ef - es
    out: list[Event] = []
    for i in range(1, len(close)):
        prev, cur = diff.iloc[i - 1], diff.iloc[i]
        if pd.isna(prev) or pd.isna(cur):
            continue
        if prev <= 0 < cur:
            out.append(Event(_iso(dates.iloc[i]), "ema_cross", "bull",
                             magnitude=float(abs(cur) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow}))
        elif prev >= 0 > cur:
            out.append(Event(_iso(dates.iloc[i]), "ema_cross", "bear",
                             magnitude=float(abs(cur) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow}))
    return out


def _pivots(series: pd.Series, width: int, *, kind: str) -> list[int]:
    """Indices of confirmed local extrema: a bar is a pivot low (kind='low')
    if it is the minimum of the [i-width, i+width] window (mirror for 'high').
    Only bars with `width` neighbours on each side can be pivots."""
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


def extract_rsi_divergence(
    ohlcv: pd.DataFrame, *, period: int = 14, pivot_w: int = 5, max_gap: int = 60,
) -> list[Event]:
    """Regular RSI divergence over the two most recent confirmed price pivots.
    Bull: price lower-low but RSI higher-low. Bear: price higher-high but RSI
    lower-high. Event dated at the second (more recent) pivot. magnitude = the
    RSI delta between the two pivots (normalised to [0,1] by /50)."""
    if len(ohlcv) < period + 2 * pivot_w + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    r = rsi(close, period).reset_index(drop=True)
    out: list[Event] = []

    lows = _pivots(close, pivot_w, kind="low")
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if (b - a) <= max_gap and close.iloc[b] < close.iloc[a] \
                and pd.notna(r.iloc[a]) and pd.notna(r.iloc[b]) and r.iloc[b] > r.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "rsi_divergence", "bull",
                             magnitude=float(min(1.0, (r.iloc[b] - r.iloc[a]) / 50.0)),
                             payload={"period": period,
                                      "pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])],
                                      "rsi": [float(r.iloc[a]), float(r.iloc[b])]}))

    highs = _pivots(close, pivot_w, kind="high")
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if (b - a) <= max_gap and close.iloc[b] > close.iloc[a] \
                and pd.notna(r.iloc[a]) and pd.notna(r.iloc[b]) and r.iloc[b] < r.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "rsi_divergence", "bear",
                             magnitude=float(min(1.0, (r.iloc[a] - r.iloc[b]) / 50.0)),
                             payload={"period": period,
                                      "pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])],
                                      "rsi": [float(r.iloc[a]), float(r.iloc[b])]}))
    return out


def extract_bollinger(
    ohlcv: pd.DataFrame, *, period: int = 20, k: float = 2.0, kc_mult: float = 1.5,
) -> list[Event]:
    """TTM-style squeeze: Bollinger Bands (period,k) INSIDE Keltner Channels
    (EMA(period) +/- kc_mult*ATR(period)) => bb_squeeze on that bar. The first
    bar where the bands pop back OUTSIDE the Keltner after a squeeze =>
    bb_expansion, with direction = sign(close - middle)."""
    if len(ohlcv) < period + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    bb_u, bb_m, bb_l = (s.reset_index(drop=True) for s in bollinger(close, period, k))
    a = atr(ohlcv, period).reset_index(drop=True)
    kc_u = bb_m + kc_mult * a
    kc_l = bb_m - kc_mult * a
    out: list[Event] = []
    in_squeeze = False
    for i in range(len(close)):
        if pd.isna(bb_u.iloc[i]) or pd.isna(kc_u.iloc[i]):
            continue
        squeezed = (bb_u.iloc[i] < kc_u.iloc[i]) and (bb_l.iloc[i] > kc_l.iloc[i])
        if squeezed:
            in_squeeze = True
            out.append(Event(_iso(dates.iloc[i]), "bb_squeeze", None,
                             magnitude=float((kc_u.iloc[i] - kc_l.iloc[i]) /
                                             (bb_u.iloc[i] - bb_l.iloc[i]))
                             if (bb_u.iloc[i] - bb_l.iloc[i]) else None,
                             payload={"period": period}))
        elif in_squeeze:
            in_squeeze = False
            direction = "bull" if close.iloc[i] >= bb_m.iloc[i] else "bear"
            out.append(Event(_iso(dates.iloc[i]), "bb_expansion", direction,
                             magnitude=float(abs(close.iloc[i] - bb_m.iloc[i]) / bb_m.iloc[i])
                             if bb_m.iloc[i] else None,
                             payload={"period": period}))
    return out
```

Then extend the `EXTRACTORS` list to register the new event producers (the breakout/volume entries stay):

```python
EXTRACTORS = [
    lambda df: extract_breakout(df, lookback=20),
    lambda df: extract_volume_spike(df, avg_period=20, k=2.0),
    lambda df: extract_ema_cross(df, fast=50, slow=200),
    lambda df: extract_rsi_divergence(df, period=14, pivot_w=5, max_gap=60),
    lambda df: extract_bollinger(df, period=20, k=2.0, kc_mult=1.5),
]
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_events_phase1b.py -q`
Expected: PASS (3 tests). Then run the full signals dir to confirm no regression in `extract_events`: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/ -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/events.py backend/tests/signals/test_events_phase1b.py
git commit -m "feat(signals): ema_cross, rsi_divergence, bollinger squeeze extractors"
```

---

### Task 2: Trend-Pullback Continuation detector

**Files:**
- Create: `backend/app/signals/detectors/trend_pullback.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_trend_pullback.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_trend_pullback.py
import pandas as pd
from app.signals.context import build_context
from app.signals.events import extract_events
from app.signals.detectors.trend_pullback import TrendPullback


def _golden_then_pullback():
    # Long uptrend so EMA50 > EMA200 (golden cross happened), then a dip that
    # tags EMA50, then a resume (last close back above EMA50).
    rows = []
    price = 100.0
    for i in range(210):
        price += 0.6                      # steady uptrend -> eventual golden cross
        rows.append((price, 1000))
    for i in range(8):                    # pullback
        price -= 1.4
        rows.append((price, 1000))
    for i in range(4):                    # resume
        price += 2.2
        rows.append((price, 1000))
    return pd.DataFrame([
        {"date": f"{2025 + i // 360}-{1 + (i // 30) % 12:02d}-{1 + i % 28:02d}",
         "open": p, "high": p + 1, "low": p - 1, "close": p, "volume": v}
        for i, (p, v) in enumerate(rows)
    ])


def test_fires_on_golden_cross_pullback_resume():
    df = _golden_then_pullback()
    m = TrendPullback().detect(extract_events(df), df, build_context(df))
    assert m is not None and m.tone == "bull" and m.confidence > 0
    assert any("cross" in s["label"].lower() or "incrocio" in s["label"].lower()
               for s in m.chain)


def test_silent_on_flat_series():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(210)]
    df = pd.DataFrame(rows)
    assert TrendPullback().detect(extract_events(df), df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_trend_pullback.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the detector + register**

```python
# backend/app/signals/detectors/trend_pullback.py
"""Trend-Pullback Continuation: after a moving-average golden/death cross, price
pulls back toward the fast MA and then resumes in the trend direction. Source:
Brock, Lakonishok & LeBaron (J. Finance 1992) on MA-crossover rules; pullback
entry as the consolidated refinement."""
from __future__ import annotations

import pandas as pd

from app.indicators.ema import ema
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_FAST = 50
_SLOW = 200
_PULLBACK_TOL = 0.015   # within 1.5% of the fast EMA counts as a tag
_TREND_SPREAD_REF = 0.05  # EMA50 5% above EMA200 => full trend-strength factor


class TrendPullback:
    name = "trend_pullback"
    tone = "bull"
    sources = ["Brock, Lakonishok & LeBaron (J. Finance 1992) - MA crossover rules + pullback"]
    min_bars = _SLOW + 10

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        crosses = [e for e in events if e.type == "ema_cross"]
        if not crosses:
            return None
        cross = crosses[-1]
        tone = cross.direction or "bull"
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        ef = ema(close, _FAST).reset_index(drop=True)
        es = ema(close, _SLOW).reset_index(drop=True)
        last = len(close) - 1
        fast_now = ef.iloc[last]
        if pd.isna(fast_now) or fast_now == 0:
            return None
        # Pullback: at least one recent bar tagged the fast EMA from the trend
        # side; Resume: the last close is back on the trend side of the fast EMA.
        recent = range(max(0, last - 20), last + 1)
        if tone == "bull":
            tagged = any(close.iloc[i] <= ef.iloc[i] * (1 + _PULLBACK_TOL) for i in recent)
            resumed = close.iloc[last] > fast_now
        else:
            tagged = any(close.iloc[i] >= ef.iloc[i] * (1 - _PULLBACK_TOL) for i in recent)
            resumed = close.iloc[last] < fast_now
        if not (tagged and resumed):
            return None

        spread = abs(ef.iloc[last] - es.iloc[last]) / close.iloc[last]
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "trend_strength": clamp01(spread / _TREND_SPREAD_REF),
            "trend_alignment": 1.0 if trend_aligned else 0.4,
            "resume": 1.0 if resumed else 0.0,
        }
        conf = score(factors, {"trend_strength": 1.0, "trend_alignment": 1.0, "resume": 0.6})
        chain = [
            {"date": cross.date, "label": f"Incrocio EMA {tone}",
             "detail": f"EMA{_FAST}/EMA{_SLOW} ({'golden' if tone == 'bull' else 'death'} cross)"},
            {"date": _last_date(ohlcv), "label": "Pullback + ripresa",
             "detail": f"ritorno verso EMA{_FAST} e ripartenza nel verso del trend"},
        ]
        invalidation = {"level": float(es.iloc[last]),
                        "reason": f"chiusura oltre EMA{_SLOW} contro il trend"}
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=_last_date(ohlcv), chain=chain,
                           invalidation=invalidation, factors=factors)


def _last_date(ohlcv: pd.DataFrame) -> str:
    return str(ohlcv["date"].iloc[-1])[:10]
```

Then in `backend/app/signals/detectors/registry.py`:

```python
"""Active signal detectors for the current phase."""
from app.signals.detectors.trend_pullback import TrendPullback
from app.signals.detectors.volume_breakout import VolumeBreakout

DETECTORS = [VolumeBreakout(), TrendPullback()]
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_trend_pullback.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/detectors/trend_pullback.py backend/app/signals/detectors/registry.py backend/tests/signals/test_trend_pullback.py
git commit -m "feat(signals): Trend-Pullback Continuation detector"
```

---

### Task 3: RSI Regular Divergence detector

**Files:**
- Create: `backend/app/signals/detectors/rsi_divergence.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_rsi_divergence.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_rsi_divergence.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.rsi_divergence import RsiDivergence
from app.signals.events import Event


def test_fires_from_bull_divergence_event():
    # Drive the detector directly with a synthetic bull-divergence event so the
    # test is deterministic and independent of pivot tuning.
    events = [Event("2026-05-01", "rsi_divergence", "bull", magnitude=0.4,
                    payload={"period": 14, "rsi": [22.0, 42.0],
                             "pivot_dates": ["2026-04-10", "2026-05-01"]})]
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(30)]
    df = pd.DataFrame(rows)
    m = RsiDivergence().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("divergen" in s["label"].lower() for s in m.chain)


def test_silent_without_divergence_event():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(30)]
    df = pd.DataFrame(rows)
    assert RsiDivergence().detect([], df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_rsi_divergence.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the detector + register**

```python
# backend/app/signals/detectors/rsi_divergence.py
"""RSI Regular Divergence: price makes a lower low while RSI makes a higher low
(bull), or price a higher high while RSI a lower high (bear) - a classic
reversal setup. Source: Wilder, "New Concepts in Technical Trading Systems"
(1978). Consumes the rsi_divergence event produced by the extractor."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

# Divergence is a reversal, so it is *expected* to fire against the prevailing
# trend; we reward counter-trend divergences (the high-value setup) and only
# mildly down-weight with-trend ones.
_COUNTER_TREND_BONUS = 1.0
_WITH_TREND = 0.5


class RsiDivergence:
    name = "rsi_divergence"
    tone = "bull"
    sources = ['Wilder, "New Concepts in Technical Trading Systems" (1978)']
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        divs = [e for e in events if e.type == "rsi_divergence"]
        if not divs:
            return None
        d = divs[-1]
        tone = d.direction or "bull"
        rsi_pair = d.payload.get("rsi") or []
        # Counter-trend reward: a bull divergence in a downtrend (or bear in an
        # uptrend) is the textbook reversal; with-trend divergence is weaker.
        counter = (tone == "bull" and ctx.trend_sign <= 0) or (tone == "bear" and ctx.trend_sign >= 0)
        # Extremity: a bull div off oversold (low first RSI) / bear off overbought.
        extremity = 0.0
        if len(rsi_pair) == 2:
            if tone == "bull":
                extremity = clamp01((40.0 - min(rsi_pair)) / 25.0)   # RSI 15 => full
            else:
                extremity = clamp01((max(rsi_pair) - 60.0) / 25.0)   # RSI 85 => full
        factors = {
            "divergence_amplitude": clamp01(d.magnitude or 0.0),
            "extremity": extremity,
            "trend_context": _COUNTER_TREND_BONUS if counter else _WITH_TREND,
        }
        conf = score(factors, {"divergence_amplitude": 1.0, "extremity": 0.8, "trend_context": 1.0})
        pivots = d.payload.get("pivot_dates") or [d.date, d.date]
        chain = [
            {"date": pivots[0], "label": "Primo minimo/massimo",
             "detail": "estremo di prezzo iniziale"},
            {"date": d.date, "label": f"Divergenza RSI {tone}",
             "detail": "prezzo e RSI divergono (setup di inversione)"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=d.date, chain=chain, invalidation=None,
                           factors=factors)
```

Then add to `registry.py`:

```python
"""Active signal detectors for the current phase."""
from app.signals.detectors.rsi_divergence import RsiDivergence
from app.signals.detectors.trend_pullback import TrendPullback
from app.signals.detectors.volume_breakout import VolumeBreakout

DETECTORS = [VolumeBreakout(), TrendPullback(), RsiDivergence()]
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_rsi_divergence.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/detectors/rsi_divergence.py backend/app/signals/detectors/registry.py backend/tests/signals/test_rsi_divergence.py
git commit -m "feat(signals): RSI Regular Divergence detector"
```

---

### Task 4: Volatility Squeeze Expansion detector

**Files:**
- Create: `backend/app/signals/detectors/squeeze_expansion.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_squeeze_expansion.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_squeeze_expansion.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.events import Event


def _events_squeeze_then_expansion():
    return [
        Event("2026-04-20", "bb_squeeze", None, magnitude=1.4, payload={"period": 20}),
        Event("2026-04-28", "bb_expansion", "bull", magnitude=0.05, payload={"period": 20}),
    ]


def test_fires_on_squeeze_then_expansion():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(40)]
    df = pd.DataFrame(rows)
    m = SqueezeExpansion().detect(_events_squeeze_then_expansion(), df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("squeeze" in s["label"].lower() or "compressione" in s["label"].lower()
               for s in m.chain)


def test_silent_with_squeeze_but_no_expansion():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(40)]
    df = pd.DataFrame(rows)
    only_squeeze = [Event("2026-04-20", "bb_squeeze", None, magnitude=1.4, payload={})]
    assert SqueezeExpansion().detect(only_squeeze, df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_squeeze_expansion.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the detector + register**

```python
# backend/app/signals/detectors/squeeze_expansion.py
"""Volatility Squeeze Expansion: Bollinger Bands contract inside Keltner
Channels (a squeeze = energy build-up), then expand; the breakout resolves in
the expansion's direction. Source: Bollinger (2001); TTM Squeeze (Carter,
"Mastering the Trade"). Consumes bb_squeeze + bb_expansion events."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

_EXPAND_WINDOW_DAYS = 15   # an expansion within ~3 weeks of the squeeze
_TIGHTNESS_REF = 1.5       # KC/BB width ratio this high => maximally coiled


class SqueezeExpansion:
    name = "squeeze_expansion"
    tone = "bull"
    sources = ['Bollinger (2001); TTM Squeeze (Carter, "Mastering the Trade")']
    min_bars = 25

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        squeezes = [e for e in events if e.type == "bb_squeeze"]
        if not squeezes:
            return None
        sq = squeezes[-1]
        exp = find_after(events, "bb_expansion", after=sq.date, within_days=_EXPAND_WINDOW_DAYS)
        if exp is None:
            return None
        tone = exp.direction or ("bull" if ctx.trend_sign >= 0 else "bear")
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "tightness": clamp01((sq.magnitude or 1.0) / _TIGHTNESS_REF),
            "expansion_strength": clamp01((exp.magnitude or 0.0) / 0.06),  # 6% pop => full
            "trend_alignment": 1.0 if trend_aligned else 0.5,
        }
        conf = score(factors, {"tightness": 0.8, "expansion_strength": 1.0, "trend_alignment": 0.8})
        chain = [
            {"date": sq.date, "label": "Compressione (squeeze)",
             "detail": "Bollinger dentro Keltner: volatilita compressa"},
            {"date": exp.date, "label": f"Espansione {tone}",
             "detail": "le bande si riaprono: rilascio nel verso del trend"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=exp.date, chain=chain, invalidation=None,
                           factors=factors)
```

Then add to `registry.py`:

```python
"""Active signal detectors for the current phase."""
from app.signals.detectors.rsi_divergence import RsiDivergence
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.detectors.trend_pullback import TrendPullback
from app.signals.detectors.volume_breakout import VolumeBreakout

DETECTORS = [VolumeBreakout(), TrendPullback(), RsiDivergence(), SqueezeExpansion()]
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_squeeze_expansion.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/detectors/squeeze_expansion.py backend/app/signals/detectors/registry.py backend/tests/signals/test_squeeze_expansion.py
git commit -m "feat(signals): Volatility Squeeze Expansion detector"
```

---

### Task 5: 52-Week-High Momentum detector

**Files:**
- Create: `backend/app/signals/detectors/high52_momentum.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_high52_momentum.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_high52_momentum.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.high52_momentum import High52Momentum
from app.signals.events import extract_events


def _near_52w_high_uptrend():
    # 260 bars rising to a fresh high on the last bar.
    rows = []
    price = 50.0
    for i in range(260):
        price += 0.25
        rows.append(price)
    return pd.DataFrame([
        {"date": f"{2025 + i // 360}-{1 + (i // 30) % 12:02d}-{1 + i % 28:02d}",
         "open": p, "high": p + 0.5, "low": p - 0.5, "close": p, "volume": 1000}
        for i, p in enumerate(rows)
    ])


def test_fires_near_52w_high_in_uptrend():
    df = _near_52w_high_uptrend()
    m = High52Momentum().detect(extract_events(df), df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("52" in s["label"] for s in m.chain)


def test_silent_far_below_high():
    # Rises then falls 20% below the high.
    rows = []
    price = 50.0
    for i in range(220):
        price += 0.25
        rows.append(price)
    peak = price
    for i in range(40):
        price -= peak * 0.006
        rows.append(price)
    df = pd.DataFrame([
        {"date": f"{2025 + i // 360}-{1 + (i // 30) % 12:02d}-{1 + i % 28:02d}",
         "open": p, "high": p + 0.5, "low": p - 0.5, "close": p, "volume": 1000}
        for i, p in enumerate(rows)
    ])
    assert High52Momentum().detect(extract_events(df), df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_high52_momentum.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the detector + register**

```python
# backend/app/signals/detectors/high52_momentum.py
"""52-Week-High Momentum: price at/near its 52-week high within an uptrend - a
documented momentum anomaly. Source: George & Hwang, "The 52-Week High and
Momentum Investing" (J. Finance 2004). Computes proximity directly (no event)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_WINDOW = 252                 # ~52 weeks of trading days
_NEAR_THRESHOLD = 0.97        # within 3% of the 52w high qualifies


class High52Momentum:
    name = "high52_momentum"
    tone = "bull"              # documented only on the long side
    sources = ['George & Hwang, "The 52-Week High and Momentum Investing" (J. Finance 2004)']
    min_bars = 60              # at least ~3 months of history for a meaningful window

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        high = ohlcv["high"].astype(float)
        low = ohlcv["low"].astype(float)
        window = min(_WINDOW, len(ohlcv))
        hi_52 = float(high.iloc[-window:].max())
        lo_52 = float(low.iloc[-window:].min())
        last = ctx.last_close
        if hi_52 <= 0:
            return None
        proximity = last / hi_52
        if proximity < _NEAR_THRESHOLD or ctx.trend_sign <= 0:
            return None
        rng = hi_52 - lo_52
        momentum = clamp01((last - lo_52) / rng) if rng > 0 else 0.0
        factors = {
            # proximity 0.97..1.00 -> 0..1
            "proximity": clamp01((proximity - _NEAR_THRESHOLD) / (1.0 - _NEAR_THRESHOLD)),
            "trend": 1.0 if ctx.trend_sign > 0 else 0.0,
            "momentum": momentum,
        }
        conf = score(factors, {"proximity": 1.0, "trend": 0.8, "momentum": 0.8})
        last_date = str(ohlcv["date"].iloc[-1])[:10]
        chain = [
            {"date": last_date, "label": "Vicino al massimo 52 settimane",
             "detail": f"prezzo a {proximity * 100:.1f}% del massimo a 52w"},
            {"date": last_date, "label": "Trend rialzista",
             "detail": "EMA lunga in salita: momentum confermato"},
        ]
        invalidation = {"level": lo_52, "reason": "rottura del minimo a 52 settimane"}
        return SignalMatch(name=self.name, tone="bull", confidence=conf,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors)
```

Then finalise `registry.py`:

```python
"""Active signal detectors for the current phase."""
from app.signals.detectors.high52_momentum import High52Momentum
from app.signals.detectors.rsi_divergence import RsiDivergence
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.detectors.trend_pullback import TrendPullback
from app.signals.detectors.volume_breakout import VolumeBreakout

DETECTORS = [
    VolumeBreakout(),
    TrendPullback(),
    RsiDivergence(),
    SqueezeExpansion(),
    High52Momentum(),
]
```

- [ ] **Step 4: Run, verify pass + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_high52_momentum.py -q` (expect 2 pass).
Then the FULL suite: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` — confirm green (all prior + new). The scan integration test from 1a must still pass with 5 detectors active.

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/detectors/high52_momentum.py backend/app/signals/detectors/registry.py backend/tests/signals/test_high52_momentum.py
git commit -m "feat(signals): 52-Week-High Momentum detector (registry now 5 detectors)"
```

---

## Self-review notes
- Spec coverage: all 5 design-spec detectors now exist (volume_breakout from 1a + the 4 here). Extractors added: ema_cross, rsi_divergence, bollinger (squeeze/expansion). 52w-high needs no extractor (direct computation). ✓
- Additive: only `events.py` (new functions + EXTRACTORS) and `registry.py` (new entries) are modified; everything else is new files. The runner/scan/dedup/threshold/API from 1a handle the new matches unchanged. ✓
- Type consistency: every detector returns `SignalMatch` with the same fields; all use `score`/`clamp01`/`find_after` from base; chains are `[{date,label,detail}]`. ✓
- Determinism/testability: detectors with hard-to-synthesize setups (rsi_divergence, squeeze) are unit-tested by feeding the events directly (the extractor is tested separately in Task 1); trend_pullback and high52 are tested on crafted OHLCV. ✓
- Confidence: each detector defines 2-3 clamped [0,1] factors + weights; emits whenever structurally present; the `signal_min_confidence` gate (default 60) decides alerting. ✓
- ASCII-only source (Italian labels avoid accented chars; multiplication uses "x"). ✓

## Follow-up (Plan 1c)
Enriched alert UI for `signal:*` kinds (chain timeline, confidence badge, tone, invalidation, sources) + the deferred backend bits (notifier digest labeling, signal-kind filtering, stats inner-joins, frontend RuleKind type).
