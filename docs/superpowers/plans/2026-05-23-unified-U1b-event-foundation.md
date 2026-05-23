# Unified Signals — Phase U1b: event-layer foundation + first new confirmed signal

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Lay the technical-event foundation for the expanded catalog — a shared pivot engine, an `Event.source` field, two new atomic event extractors (RSI extreme, support/resistance levels) — and ship one new confirmed detector (Oversold/Overbought Reversal at S/R) plus tighten `high52_momentum` to honor the "atomic-never-alone" rule.

**Architecture:** Additive on the proven signal framework. Atomic extractors stay un-surfaced (they only feed detectors). The multi-source `gather_events` seam is intentionally DEFERRED to U3 (when non-technical producers arrive) — U1b is technical-pure. Decided with the user.

**Tech Stack:** Python 3.11, pandas, pytest. Reuses `app/indicators/` (rsi) + the existing signal scaffold.

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; full suite must stay green (currently 571 passed / 1 skipped). ASCII-only source.

---

### Task 1: Shared pivot engine + Event.source field

**Files:**
- Create: `backend/app/signals/pivots.py`
- Modify: `backend/app/signals/events.py` (move `_pivots` out; add `source` to `Event`)
- Modify: `backend/tests/signals/test_events_phase1b.py` (import path for the pivot helper)
- Test: `backend/tests/signals/test_pivots.py`

- [ ] **Step 1: Write the failing test**
```python
# backend/tests/signals/test_pivots.py
import pandas as pd
from app.signals.pivots import find_pivots


def test_find_pivots_extrema_and_edges():
    s = pd.Series([5, 3, 1, 4, 2, 6, 0])
    assert find_pivots(s, 1, kind="low") == [2, 4]
    assert find_pivots(s, 1, kind="high") == [3, 5]
    edges = find_pivots(s, 1, kind="low") + find_pivots(s, 1, kind="high")
    assert 0 not in edges and 6 not in edges
```

- [ ] **Step 2: Run, verify fail** — `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_pivots.py -q` → ImportError.

- [ ] **Step 3: Create `pivots.py`** (move the body of the existing `_pivots` in `events.py`):
```python
# backend/app/signals/pivots.py
"""Confirmed swing-pivot detection shared across detectors (divergence, S/R,
geometric patterns). A bar is a pivot only if it has `width` neighbours on
each side that it dominates — so the most recent confirmable pivot lags by
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
```

- [ ] **Step 4: Update `events.py`**
- Add `from app.signals.pivots import find_pivots` near the top.
- DELETE the local `_pivots` function.
- In `extract_rsi_divergence`, replace `_pivots(close, pivot_w, kind="low")` / `kind="high"` calls with `find_pivots(...)`.
- Add a `source` field to the `Event` dataclass (default keeps every existing call working):
```python
@dataclass(frozen=True)
class Event:
    date: str
    type: str
    direction: str | None = None
    magnitude: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "technical"   # "technical" | "earnings" | "analyst" | "insider"
```

- [ ] **Step 5: Update the old `_pivots` test** — in `backend/tests/signals/test_events_phase1b.py` change the import `from app.signals.events import (_pivots, ...)` to import `find_pivots` from `app.signals.pivots`, and update the `test_pivots_...` call sites to `find_pivots`. (Or delete that test from this file since `test_pivots.py` now covers it — pick one; do not leave a broken import.)

- [ ] **Step 6: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/ -q` → green.
```bash
git add backend/app/signals/pivots.py backend/app/signals/events.py backend/tests/signals/test_pivots.py backend/tests/signals/test_events_phase1b.py
git commit -m "feat(signals): shared pivot engine + Event.source field"
```

---

### Task 2: New atomic extractors — RSI extreme + S/R levels

**Files:**
- Modify: `backend/app/signals/events.py`
- Test: `backend/tests/signals/test_events_atomic.py`

- [ ] **Step 1: Write the failing tests**
```python
# backend/tests/signals/test_events_atomic.py
import pandas as pd
from app.signals.events import extract_rsi_extreme, extract_sr_levels


def _df(closes):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def test_rsi_extreme_emits_oversold_on_sharp_drop():
    closes = [100] * 20 + [100 - i * 4 for i in range(1, 12)]  # steep decline -> low RSI
    evs = extract_rsi_extreme(_df(closes), period=14, low=30, high=70)
    assert any(e.type == "rsi_extreme" and e.direction == "bull" for e in evs)


def test_sr_levels_emit_support_and_resistance():
    # zig-zag so there are clear pivot highs/lows
    closes = []
    for _ in range(4):
        closes += [100, 104, 108, 104, 100, 96, 92, 96, 100]
    evs = extract_sr_levels(_df(closes), width=2)
    kinds = {e.payload.get("kind") for e in evs if e.type == "sr_level"}
    assert "support" in kinds and "resistance" in kinds
```

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement in `events.py`** (after `extract_bollinger`, before the `EXTRACTORS` list). Import rsi at top if not already: `from app.indicators.rsi import rsi` (already imported in Phase 1b — reuse). `find_pivots` is imported (Task 1).
```python
def extract_rsi_extreme(
    ohlcv: pd.DataFrame, *, period: int = 14, low: float = 30.0, high: float = 70.0,
) -> list[Event]:
    """Emit rsi_extreme on each bar where RSI <= low (bull=oversold) or
    RSI >= high (bear=overbought). magnitude = how far past the threshold,
    normalised by the threshold distance to 0/100."""
    if len(ohlcv) < period + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    r = rsi(close, period).reset_index(drop=True)
    out: list[Event] = []
    for i in range(len(close)):
        v = r.iloc[i]
        if pd.isna(v):
            continue
        if v <= low:
            out.append(Event(_iso(dates.iloc[i]), "rsi_extreme", "bull",
                             magnitude=float((low - v) / low) if low else None,
                             payload={"rsi": float(v), "period": period}))
        elif v >= high:
            out.append(Event(_iso(dates.iloc[i]), "rsi_extreme", "bear",
                             magnitude=float((v - high) / (100.0 - high)) if high < 100 else None,
                             payload={"rsi": float(v), "period": period}))
    return out


def extract_sr_levels(ohlcv: pd.DataFrame, *, width: int = 5) -> list[Event]:
    """Emit sr_level events at confirmed swing pivots: a pivot low is a
    support level, a pivot high is a resistance level. payload carries the
    price level + kind. Consumers check proximity of the current price."""
    if len(ohlcv) < 2 * width + 2:
        return []
    high = ohlcv["high"].astype(float).reset_index(drop=True)
    low = ohlcv["low"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    out: list[Event] = []
    for i in find_pivots(low, width, kind="low"):
        out.append(Event(_iso(dates.iloc[i]), "sr_level", None,
                         magnitude=None,
                         payload={"kind": "support", "level": float(low.iloc[i])}))
    for i in find_pivots(high, width, kind="high"):
        out.append(Event(_iso(dates.iloc[i]), "sr_level", None,
                         magnitude=None,
                         payload={"kind": "resistance", "level": float(high.iloc[i])}))
    return out
```
Then extend `EXTRACTORS` (keep existing 5, add 2):
```python
    lambda df: extract_rsi_extreme(df, period=14, low=30.0, high=70.0),
    lambda df: extract_sr_levels(df, width=5),
```

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_events_atomic.py tests/signals/ -q` → green.
```bash
git add backend/app/signals/events.py backend/tests/signals/test_events_atomic.py
git commit -m "feat(signals): rsi_extreme + sr_level atomic extractors"
```

---

### Task 3: OversoldReversal detector (first new confirmed signal)

**Files:**
- Create: `backend/app/signals/detectors/oversold_reversal.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_oversold_reversal.py`

- [ ] **Step 1: Write the failing test** (event-injection for determinism):
```python
# backend/tests/signals/test_oversold_reversal.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.oversold_reversal import OversoldReversal
from app.signals.events import Event


def _df(last_close, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def test_fires_oversold_at_support_with_turn_up():
    df = _df(96.5)   # last close just above the 96 support
    events = [
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.5,
              payload={"rsi": 22.0, "period": 14}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = OversoldReversal().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("ipervendut" in s["label"].lower() or "supporto" in s["label"].lower()
               for s in m.chain)


def test_silent_without_rsi_extreme():
    df = _df(96.5)
    only_sr = [Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0})]
    assert OversoldReversal().detect(only_sr, df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/oversold_reversal.py
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
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) >= 2 else last
        # Confirmation 1: price near a matching S/R level.
        want = "support" if tone == "bull" else "resistance"
        levels = [e.payload.get("level") for e in events
                  if e.type == "sr_level" and e.payload.get("kind") == want
                  and isinstance(e.payload.get("level"), (int, float))]
        near = any(abs(last - lv) / lv <= _NEAR_PCT for lv in levels if lv) if levels else False
        if not near:
            return None
        # Confirmation 2: the last bar turns in the reversal direction.
        turned = (last > prev) if tone == "bull" else (last < prev)
        if not turned:
            return None
        rsi_v = ext.payload.get("rsi")
        extremity = clamp01((30.0 - rsi_v) / 25.0) if (tone == "bull" and isinstance(rsi_v, (int, float))) \
            else clamp01((rsi_v - 70.0) / 25.0) if isinstance(rsi_v, (int, float)) else 0.0
        factors = {
            "rsi_extremity": extremity,
            "at_level": 1.0,            # gate (kept for display)
            "turn": 1.0,                # gate (kept for display)
        }
        conf = score(factors, {"rsi_extremity": 1.0})  # gates excluded from weights
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
```
Add to `registry.py` (append):
```python
from app.signals.detectors.oversold_reversal import OversoldReversal
# ... DETECTORS = [VolumeBreakout(), TrendPullback(), RsiDivergence(),
#                  SqueezeExpansion(), High52Momentum(), OversoldReversal()]
```

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_oversold_reversal.py tests/signals/ -q` → green.
```bash
git add backend/app/signals/detectors/oversold_reversal.py backend/app/signals/detectors/registry.py backend/tests/signals/test_oversold_reversal.py
git commit -m "feat(signals): Oversold/Overbought Reversal at S/R detector"
```

---

### Task 4: Tighten high52_momentum (require a confirmation)

**Files:**
- Modify: `backend/app/signals/detectors/high52_momentum.py`
- Test: `backend/tests/signals/test_high52_momentum.py`

- [ ] **Step 1: Update the test** — high52 must now ALSO require a recent breakout OR volume_spike event (so it is not bare proximity+trend). Adapt the existing positive test to pass events that include a breakout near the high; add a negative test that proximity+trend WITHOUT a breakout/volume event → None:
```python
def test_silent_near_high_without_confirmation():
    df = _near_52w_high_uptrend()           # near-high + uptrend
    # no breakout / volume_spike events supplied
    assert High52Momentum().detect([], df, build_context(df)) is None
```
For the positive test, pass `extract_events(df)` (which yields a Donchian breakout on the fresh-high last bar) so the confirmation is present.

- [ ] **Step 2: Implement** — in `detect`, after the proximity + trend gates, require a confirming event:
```python
        confirmed = any(
            e.type in ("breakout", "volume_spike")
            for e in events
        )
        if not confirmed:
            return None
```
Place this BEFORE building the SignalMatch. Add a third chain step describing the confirmation, and add a `confirmation` factor (1.0, a gate — kept for display, excluded from weights). Keep the existing `proximity`/`momentum` weighting.

- [ ] **Step 3: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_high52_momentum.py tests/signals/ -q` → green.
```bash
git add backend/app/signals/detectors/high52_momentum.py backend/tests/signals/test_high52_momentum.py
git commit -m "refactor(signals): high52_momentum requires a breakout/volume confirmation"
```

---

### Task 5: Polish — signal-performance label + dead rule metadata

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx` (label), `frontend/src/lib/alertMeta.ts` (remove dead rule metadata)
- Verify: `cd frontend && npm run build`

- [ ] **Step 1: Rename label** — in `SettingsPage.tsx` change "Efficacia regole" / "Statistiche di efficacia delle regole" to "Efficacia segnali" / "Statistiche di efficacia dei segnali" (forward-return). Grep the file for "regole" and update the rule-performance card copy (NOT unrelated text).
- [ ] **Step 2: Remove dead rule metadata** in `alertMeta.ts`: delete the rule-kind entries in `META_BY_KIND` (rsi_oversold, rsi_overbought, golden_cross, death_cross, volume_spike, breakout, macd_*, bollinger_breakout, adx_*, gap_*, mean_reversion_*, composite) — keep `getAlertKindMeta`'s fallback. Delete the per-rule `case` blocks in `resolveSnapshot` and `getSnapshotHeadline` (keep the signal branch + the price-alert/default handling). KEEP `getAlertMeta`'s signal + price-alert branches, the TONE_* maps, `isSignalKind`, `SIGNAL_META`. The signal feed/detail must still render.
- [ ] **Step 3: Build + commit**
`cd frontend && npm run build` → tsc + vite clean. Rebuild dist (this build writes it).
```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/lib/alertMeta.ts
git commit -m "polish(ui): signal-performance label + drop dead rule metadata"
```

---

## Self-review notes
- Decisions honored: foundations + 1 visible detector (T3) ✓; gather_events deferred to U3 (no multi-source code here) ✓; high52 tightened to require confirmation (T4) ✓.
- Spec coverage (master §3-4 foundation): shared pivot engine (T1), Event.source (T1), expanded atomic events rsi_extreme + sr_level (T2), first confirmed reversal detector (T3). The remaining atomic events (macd_cross/divergence, adx, gap, obv) + the other detectors are U2. ✓
- Atomic-never-alone: rsi_extreme + sr_level are extractors only (not in registry); OversoldReversal requires extreme + at-level + turn (3 events); high52 now requires a confirmation. ✓
- Type consistency: `find_pivots`, `Event.source`, `extract_rsi_extreme`, `extract_sr_levels`, `OversoldReversal`, `score`/`clamp01` used consistently. Gate-confirmation factors excluded from score weights (Phase-1b lesson). ✓
- ASCII-only; full suite green gate each task. ✓
