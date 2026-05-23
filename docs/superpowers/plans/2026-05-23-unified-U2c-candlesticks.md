# Unified Signals — Phase U2c: candlestick reversals (Layer D)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Add the candlestick layer: a `candle_reversal` event extractor (engulfing, hammer/shooting-star, morning/evening star) and one confirmed `CandleReversal` detector that fires only when a reliable reversal candle sits at a support/resistance level against the prior trend.

**Architecture:** Additive. Candle shapes are EVENTS (never surfaced alone); the single `CandleReversal` detector requires candle + S/R proximity + reversal context (atomic-never-alone). Design choice (delegated): one detector that names the specific pattern in its chain, rather than ~10 separate candle detectors — cleaner and less noisy. Full suite stays green (592 passed / 1 skipped).

**Tech Stack:** Python 3.11, pandas, pytest. Reuses `sr_level` events + `SignalContext.trend_sign`.

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; ASCII-only; gate factors excluded from `score` weights.

**Candle geometry definitions (used by Task 1):** for a bar — `body = abs(close-open)`, `rng = high-low`, `upper = high-max(open,close)`, `lower = min(open,close)-low`. Bullish bar: `close>open`. All ratios guard `rng>0`.

---

### Task 1: candle_reversal extractor

**Files:**
- Create: `backend/app/signals/candles.py`
- Modify: `backend/app/signals/events.py` (import + register)
- Test: `backend/tests/signals/test_candles.py`

- [ ] **Step 1: Write the failing tests**
```python
# backend/tests/signals/test_candles.py
import pandas as pd
from app.signals.candles import extract_candle_reversal


def _df(rows):
    # rows: list of (open, high, low, close)
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
         "open": o, "high": h, "low": lo, "close": c, "volume": 1000}
        for i, (o, h, lo, c) in enumerate(rows)
    ])


def test_bullish_engulfing():
    rows = [(100, 101, 99, 100)] * 5
    rows.append((99, 100, 98, 98.5))      # small bearish
    rows.append((98, 103, 97.5, 102))     # bullish body engulfs prior body
    evs = extract_candle_reversal(_df(rows))
    assert any(e.type == "candle_reversal" and e.direction == "bull"
               and e.payload.get("pattern") == "engulfing" for e in evs)


def test_hammer():
    rows = [(100 - i, 101 - i, 99 - i, 100 - i) for i in range(6)]   # downtrend
    rows.append((95, 95.3, 90, 95.1))     # tiny body on top, long lower wick
    evs = extract_candle_reversal(_df(rows))
    assert any(e.type == "candle_reversal" and e.direction == "bull"
               and e.payload.get("pattern") == "hammer" for e in evs)


def test_shooting_star():
    rows = [(100 + i, 101 + i, 99 + i, 100 + i) for i in range(6)]   # uptrend
    rows.append((105, 110, 104.8, 105.1))  # tiny body at bottom, long upper wick
    evs = extract_candle_reversal(_df(rows))
    assert any(e.type == "candle_reversal" and e.direction == "bear"
               and e.payload.get("pattern") == "shooting_star" for e in evs)


def test_flat_series_no_pattern():
    evs = extract_candle_reversal(_df([(100, 100.5, 99.5, 100)] * 30))
    assert all(e.payload.get("pattern") not in ("engulfing", "hammer", "shooting_star")
               for e in evs) or evs == []
```

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement `backend/app/signals/candles.py`**
```python
"""Candlestick reversal patterns as dated events (never surfaced alone -
consumed + confirmed by the CandleReversal detector). Covers the reliable
single/double/triple reversals: hammer / shooting-star, bullish / bearish
engulfing, morning / evening star. Source: Nison; Bulkowski candle ranks."""
from __future__ import annotations

import pandas as pd

from app.signals.events import Event, _iso

_DOJI_BODY = 0.1     # body <= 10% of range = doji-ish (star middle)
_WICK_MULT = 2.0     # reversal wick must be >= 2x body
_RECENT = 90         # only scan the recent window


def _parts(o: float, h: float, lo: float, c: float):
    body = abs(c - o)
    rng = h - lo
    upper = h - max(o, c)
    lower = min(o, c) - lo
    return body, rng, upper, lower


def extract_candle_reversal(ohlcv: pd.DataFrame, *, lookback: int = _RECENT) -> list[Event]:
    if len(ohlcv) < 4:
        return []
    o = ohlcv["open"].astype(float).reset_index(drop=True)
    h = ohlcv["high"].astype(float).reset_index(drop=True)
    lo = ohlcv["low"].astype(float).reset_index(drop=True)
    c = ohlcv["close"].astype(float).reset_index(drop=True)
    d = ohlcv["date"].reset_index(drop=True)
    n = len(c)
    start = max(2, n - lookback)
    out: list[Event] = []

    def trend_before(i: int) -> int:
        # crude local trend over the ~5 bars before i: +1 up / -1 down / 0
        j = max(0, i - 5)
        if c.iloc[i - 1] > c.iloc[j]:
            return 1
        if c.iloc[i - 1] < c.iloc[j]:
            return -1
        return 0

    for i in range(start, n):
        body, rng, upper, lower = _parts(o.iloc[i], h.iloc[i], lo.iloc[i], c.iloc[i])
        if rng <= 0:
            continue
        bull = c.iloc[i] > o.iloc[i]
        tb = trend_before(i)

        # Hammer (bull, after a downtrend): long lower wick, small upper.
        if tb < 0 and lower >= _WICK_MULT * body and upper <= body and body <= 0.5 * rng:
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bull",
                             magnitude=float(min(1.0, lower / rng)),
                             payload={"pattern": "hammer"}))
            continue
        # Shooting star (bear, after an uptrend): long upper wick, small lower.
        if tb > 0 and upper >= _WICK_MULT * body and lower <= body and body <= 0.5 * rng:
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bear",
                             magnitude=float(min(1.0, upper / rng)),
                             payload={"pattern": "shooting_star"}))
            continue
        # Engulfing (needs prior bar).
        po, pc = o.iloc[i - 1], c.iloc[i - 1]
        prev_bear = pc < po
        prev_bull = pc > po
        if bull and prev_bear and o.iloc[i] <= pc and c.iloc[i] >= po and body > abs(pc - po):
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bull",
                             magnitude=float(min(1.0, body / rng)),
                             payload={"pattern": "engulfing"}))
            continue
        if (not bull) and prev_bull and o.iloc[i] >= pc and c.iloc[i] <= po and body > abs(pc - po):
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bear",
                             magnitude=float(min(1.0, body / rng)),
                             payload={"pattern": "engulfing"}))
            continue
        # Morning / evening star (needs 2 prior bars).
        if i >= 2:
            b2, r2, _, _ = _parts(o.iloc[i - 2], h.iloc[i - 2], lo.iloc[i - 2], c.iloc[i - 2])
            b1, r1, _, _ = _parts(o.iloc[i - 1], h.iloc[i - 1], lo.iloc[i - 1], c.iloc[i - 1])
            star = r1 > 0 and b1 <= _DOJI_BODY * r1 * 3  # small-bodied middle
            mid2 = (o.iloc[i - 2] + c.iloc[i - 2]) / 2
            # Morning star: big bear, small body, big bull closing above mid of bar -2.
            if star and c.iloc[i - 2] < o.iloc[i - 2] and bull and c.iloc[i] > mid2:
                out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bull",
                                 magnitude=0.7, payload={"pattern": "morning_star"}))
                continue
            if star and c.iloc[i - 2] > o.iloc[i - 2] and (not bull) and c.iloc[i] < mid2:
                out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bear",
                                 magnitude=0.7, payload={"pattern": "evening_star"}))
                continue
    return out
```

- [ ] **Step 4: Register in `events.py`** — add `from app.signals.candles import extract_candle_reversal` near the top and append to `EXTRACTORS`:
```python
    lambda df: extract_candle_reversal(df),
```
(NB: `candles.py` imports `Event, _iso` from `events.py`; `events.py` imports `extract_candle_reversal` from `candles.py`. Put the `events.py` import at the BOTTOM of events.py, just before the `EXTRACTORS` list, to avoid a circular-import error at module load — or import lazily inside a thin wrapper. Verify `import app.signals.events` works.)

- [ ] **Step 5: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_candles.py tests/signals/ -q` → green. If a fixture doesn't trigger, adjust the FIXTURE.
```bash
git add backend/app/signals/candles.py backend/app/signals/events.py backend/tests/signals/test_candles.py
git commit -m "feat(signals): candle_reversal extractor (engulfing/hammer/star)"
```

---

### Task 2: CandleReversal detector

**Files:**
- Create: `backend/app/signals/detectors/candle_reversal.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_candle_reversal.py`

- [ ] **Step 1: Write the failing test** (event-injection)
```python
# backend/tests/signals/test_candle_reversal.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.candle_reversal import CandleReversal
from app.signals.events import Event


def _df(last_close, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)])


def test_fires_bull_candle_at_support():
    df = _df(96.5)
    events = [
        Event("2026-02-10", "candle_reversal", "bull", magnitude=0.8,
              payload={"pattern": "hammer"}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = CandleReversal().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("hammer" in s["detail"].lower() or "candela" in s["label"].lower()
               for s in m.chain)


def test_silent_candle_away_from_level():
    df = _df(96.5)
    events = [Event("2026-02-10", "candle_reversal", "bull", magnitude=0.8,
                    payload={"pattern": "hammer"})]   # no S/R level near price
    assert CandleReversal().detect(events, df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/candle_reversal.py
"""Candlestick Reversal (Layer D): a reliable reversal candle (engulfing,
hammer/shooting-star, morning/evening star) that forms AT a support/resistance
level - confirmed price-action reversal. Source: Nison - candlestick reliability
rises sharply at S/R with context. Confirmed: candle + at-level (never a bare
candle)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_NEAR_PCT = 0.03

_PATTERN_IT = {
    "hammer": "Hammer", "shooting_star": "Shooting star",
    "engulfing": "Engulfing", "morning_star": "Morning star",
    "evening_star": "Evening star",
}


class CandleReversal:
    name = "candle_reversal"
    tone = "bull"
    sources = ["Nison - candlestick reversals confirmed at support/resistance"]
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        candles = [e for e in events if e.type == "candle_reversal"]
        if not candles:
            return None
        cdl = candles[-1]
        tone = cdl.direction or "bull"
        last = ctx.last_close
        want = "support" if tone == "bull" else "resistance"
        levels = [e.payload.get("level") for e in events
                  if e.type == "sr_level" and e.payload.get("kind") == want
                  and isinstance(e.payload.get("level"), (int, float))]
        near = any(abs(last - lv) / lv <= _NEAR_PCT for lv in levels if lv) if levels else False
        if not near:
            return None
        pattern = cdl.payload.get("pattern", "candle")
        factors = {
            "candle_strength": clamp01(cdl.magnitude or 0.0),
            "at_level": 1.0,   # gate (display only)
        }
        conf = score(factors, {"candle_strength": 1.0})
        nearest = min((lv for lv in levels if lv), key=lambda lv: abs(last - lv))
        loc = "supporto" if tone == "bull" else "resistenza"
        chain = [
            {"date": cdl.date, "label": f"Candela di inversione {tone}",
             "detail": f"pattern {_PATTERN_IT.get(pattern, pattern)}"},
            {"date": cdl.date, "label": f"A {loc}",
             "detail": f"prezzo {last:.2f} al livello {nearest:.2f}"},
        ]
        invalidation = {"level": float(nearest), "reason": f"rottura del {loc}"}
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=cdl.date, chain=chain,
                           invalidation=invalidation, factors=factors)
```
Append `CandleReversal()` to `DETECTORS` (with import).

- [ ] **Step 4: Run + full suite + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_candle_reversal.py tests/signals/ -q` → green, then full suite. Relax any shared-fixture count test to `>= 1` if needed.
```bash
git add backend/app/signals/detectors/candle_reversal.py backend/app/signals/detectors/registry.py backend/tests/signals/test_candle_reversal.py backend/tests/
git commit -m "feat(signals): CandleReversal detector (Layer D); registry now 12"
```

---

## Self-review notes
- Candle shapes are events (in `candles.py`), never surfaced; `CandleReversal` requires candle + at-S/R (atomic-never-alone). Gate factor excluded from weights. ✓
- Circular import handled: `candles.py` imports from `events.py`; `events.py` imports `extract_candle_reversal` at the bottom (just before EXTRACTORS). Verify `import app.signals.events`. ✓
- Covers the reliable reversals (Nison/Bulkowski top): engulfing, hammer/shooting-star, morning/evening star. ✓
- Type consistency: `extract_candle_reversal`, `CandleReversal`, `score`/`clamp01`, `sr_level` payload shape consistent. ✓

## Follow-up
- **U3** — non-technical producers (`gather_events` multi-source) + earnings/analyst/insider events + hybrid signals (PEAD H1-H4).
- **U4** — geometric chart patterns on the pivot engine.
- (B7 hidden divergence: small later task — extend the divergence extractors to emit hidden + a HiddenDivergence detector.)
