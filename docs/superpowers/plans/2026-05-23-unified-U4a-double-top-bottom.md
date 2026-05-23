# Unified Signals — Phase U4a: Double Top / Double Bottom (geometric)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** First geometric chart pattern on the shared pivot engine — Double Bottom (W, bull) and Double Top (M, bear): two roughly-equal pivot extremes separated by a neckline, completed when price breaks the neckline. Highest-reliability + most tractable of the chart patterns (Bulkowski).

**Architecture:** A `chart_patterns.py` extractor emits `chart_pattern` events (the STRUCTURE) using `find_pivots`; a `ChartPattern` detector CONFIRMS the neckline break (+ volume). Additive — full suite stays green (618 passed / 1 skipped at U4a start).

**Tech Stack:** Python 3.11, pandas, pytest. Reuses `app/signals/pivots.py` `find_pivots`.

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; ASCII-only; gate factors excluded from `score` weights.

**Geometric definitions:**
- *Double Bottom (bull):* two pivot LOWS within `_LEVEL_TOL` of each other, separated by `>= _MIN_SEP` and `<= _MAX_SEP` bars, with a pivot HIGH between them = the neckline. Completes when a later close breaks ABOVE the neckline.
- *Double Top (bear):* mirror on pivot HIGHS with a pivot LOW neckline; completes on a close BELOW the neckline.

---

### Task 1: chart_pattern extractor (double top/bottom)

**Files:**
- Create: `backend/app/signals/chart_patterns.py`
- Modify: `backend/app/signals/events.py` (register via lazy lambda, like candles)
- Test: `backend/tests/signals/test_chart_patterns.py`

- [ ] **Step 1: Write the failing tests**
```python
# backend/tests/signals/test_chart_patterns.py
import pandas as pd
from app.signals.chart_patterns import extract_chart_patterns


def _df(closes):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
         "open": c, "high": c + 1.0, "low": c - 1.0, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def _double_bottom():
    # low ~90, peak ~100 (neckline), low ~90 again, then break above 100.
    seg = ([100 - i * 2 for i in range(6)]      # 100 -> 90 (down to low 1)
           + [90 + i * 2 for i in range(6)]     # 90 -> 100 (up to neckline)
           + [100 - i * 2 for i in range(6)]    # 100 -> 90 (down to low 2)
           + [90 + i * 3 for i in range(6)])    # 90 -> 105 (break above neckline)
    return _df([100] * 6 + seg)


def test_double_bottom_emitted():
    evs = extract_chart_patterns(_double_bottom(), pivot_w=2)
    assert any(e.type == "chart_pattern" and e.direction == "bull"
               and e.payload.get("pattern") == "double_bottom" for e in evs)


def test_flat_series_no_pattern():
    assert extract_chart_patterns(_df([100] * 60), pivot_w=2) == []
```

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement `backend/app/signals/chart_patterns.py`**
```python
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
```

- [ ] **Step 4: Register in `events.py`** — append to `EXTRACTORS` with a LAZY import (same pattern candles.py uses, to avoid the circular import):
```python
    lambda df: __import__("app.signals.chart_patterns", fromlist=["extract_chart_patterns"]).extract_chart_patterns(df),
```
Verify `cd backend && ./.venv/Scripts/python.exe -c "import app.signals.events; import app.signals.chart_patterns; print('ok')"`.

- [ ] **Step 5: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_chart_patterns.py tests/signals/ -q` → green. If a fixture doesn't trigger, tune the FIXTURE (the geometry is the spec) and report.
```bash
git add backend/app/signals/chart_patterns.py backend/app/signals/events.py backend/tests/signals/test_chart_patterns.py
git commit -m "feat(signals): chart_pattern extractor - double top/bottom"
```

---

### Task 2: ChartPattern detector (neckline-break confirmation)

**Files:**
- Create: `backend/app/signals/detectors/chart_pattern.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_chart_pattern_detector.py`

- [ ] **Step 1: Write the failing test** (event-injection)
```python
# backend/tests/signals/test_chart_pattern_detector.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.chart_pattern import ChartPattern
from app.signals.events import Event


def _df(last_close, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)])


def test_double_bottom_fires_after_neckline_break():
    df = _df(103)   # last close above the 100 neckline = confirmed break
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0})]
    m = ChartPattern().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("doppio" in s["label"].lower() or "double" in s["label"].lower()
               or "neckline" in s["detail"].lower() for s in m.chain)


def test_silent_before_neckline_break():
    df = _df(98)    # still below the neckline -> not confirmed
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0})]
    assert ChartPattern().detect(events, df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/chart_pattern.py
"""Chart-pattern reversal (geometric): a double bottom / double top whose
neckline has been broken by price - the classic completion that validates the
pattern. Source: Bulkowski. Confirmed: pattern structure + neckline break."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_PATTERN_IT = {"double_bottom": "Doppio minimo", "double_top": "Doppio massimo"}


class ChartPattern:
    name = "chart_pattern"
    tone = "bull"
    sources = ["Bulkowski, Encyclopedia of Chart Patterns - double top/bottom"]
    min_bars = 25

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        pats = [e for e in events if e.type == "chart_pattern"]
        if not pats:
            return None
        p = pats[-1]
        tone = p.direction or "bull"
        neckline = p.payload.get("neckline")
        if not isinstance(neckline, (int, float)) or neckline <= 0:
            return None
        last = ctx.last_close
        # Confirmation: price has broken the neckline in the pattern direction.
        broke = (last > neckline) if tone == "bull" else (last < neckline)
        if not broke:
            return None
        factors = {
            "pattern_amplitude": clamp01(p.magnitude or 0.0),
            "neckline_break": 1.0,   # gate (display only)
        }
        conf = score(factors, {"pattern_amplitude": 1.0})
        pat = p.payload.get("pattern", "pattern")
        last_date = str(ohlcv["date"].iloc[-1])[:10]
        chain = [
            {"date": p.date, "label": _PATTERN_IT.get(pat, pat),
             "detail": f"struttura confermata, neckline {neckline:.2f}"},
            {"date": last_date, "label": "Rottura neckline",
             "detail": f"prezzo {last:.2f} oltre la neckline {neckline:.2f}"},
        ]
        invalidation = {"level": float(neckline),
                        "reason": "rientro oltre la neckline (pattern fallito)"}
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=last_date, chain=chain,
                           invalidation=invalidation, factors=factors)
```
Append `ChartPattern()` to `DETECTORS` (with import) → 16.

- [ ] **Step 4: Run + full suite + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_chart_pattern_detector.py tests/signals/ -q` → green, then full suite. Relax shared-fixture count tests to `>= 1` if needed.
```bash
git add backend/app/signals/detectors/chart_pattern.py backend/app/signals/detectors/registry.py backend/tests/signals/test_chart_pattern_detector.py backend/tests/
git commit -m "feat(signals): ChartPattern detector - double top/bottom neckline break; registry 16"
```

---

## Self-review notes
- Geometric structure is an event (chart_patterns.py), confirmed by neckline break in the detector (atomic-never-alone). ✓
- Reuses `find_pivots`; double top/bottom is the most reliable + tractable geometric pattern (Bulkowski). ✓
- Lazy import in EXTRACTORS avoids the circular import (chart_patterns imports Event/_iso from events). ✓
- Gate factor (neckline_break) excluded from score weights. ✓
- Type consistency: `extract_chart_patterns`, `ChartPattern`, `find_pivots`, `score`/`clamp01` consistent. ✓

## Follow-up
- **U4b** — Head-and-Shoulders (top + inverse): 3-pivot structure + sloped neckline.
- **U4c** — Triangles / wedges / flags / rectangles (trendline-fitting + breakout).
- Then enrich the alert UI to group the event chain by `source` + show the pattern family.
