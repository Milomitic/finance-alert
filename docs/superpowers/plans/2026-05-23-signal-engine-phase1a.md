# Signal Engine — Phase 1a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the full signal-engine pipeline end-to-end with one pilot detector (Volume-Confirmed Breakout) that fires enriched alerts during the scan.

**Architecture:** New `app/signals/` package with three layers — event extractors (dated facts from OHLCV) → named detectors (consume events with time windows + transparent confidence → `SignalMatch`) → a scan hook that turns each `SignalMatch` into an `Alert` (no `Rule` row; a new nullable `Alert.signal_name` column carries the signal identity, deduped on `(stock_id, signal_name, signal_date)`).

**Tech Stack:** Python 3.11, SQLAlchemy 2 (SQLite), Alembic, pandas, pytest. Reuses `app/indicators/` (ema, rsi, atr).

**Scope note:** This plan is the vertical slice 1a (framework + 1 pilot detector + scan integration). The other 4 detectors (RSI divergence, trend-pullback, squeeze expansion, 52w-high momentum) and the enriched alert UI are follow-up plans on this same scaffolding — purely additive. See `docs/superpowers/specs/2026-05-23-signal-engine-design.md`.

**Conventions:** run tests with `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`. Alembic: `cd backend && ./.venv/Scripts/alembic.exe ...`.

---

### Task 1: Add `signal_name` column to Alert

**Files:**
- Modify: `backend/app/models/alert.py`
- Create: `backend/alembic/versions/<rev>_alert_signal_name.py`
- Test: `backend/tests/test_signal_alert_column.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_signal_alert_column.py
from datetime import date
from app.models import Alert, Stock


def test_alert_accepts_signal_name(db):
    s = Stock(ticker="ZZ_SIG", exchange="NASDAQ", name="Sig Co", country="US")
    db.add(s); db.flush()
    a = Alert(
        rule_id=None, stock_id=s.id, trigger_price=10.0,
        signal_date=date(2026, 5, 20), snapshot="{}",
        signal_name="volume_breakout",
    )
    db.add(a); db.commit()
    got = db.query(Alert).filter(Alert.signal_name == "volume_breakout").first()
    assert got is not None and got.rule_id is None
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_signal_alert_column.py -q`
Expected: FAIL — `TypeError: 'signal_name' is an invalid keyword argument for Alert`.

- [ ] **Step 3: Add the column to the model**

In `backend/app/models/alert.py`, after the `signal_date` column (line ~48) add:

```python
    # Set on alerts produced by the signal engine (rule_id is then None).
    # The "kind" surfaced to the UI is derived as f"signal:{signal_name}".
    signal_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

Add `String` to the existing `sqlalchemy` import at the top of the file if not already imported, and add to `__table_args__`:

```python
        SAIndex("ix_alerts_signal_name", "signal_name"),
```

- [ ] **Step 4: Generate + fill the migration**

Run: `cd backend && ./.venv/Scripts/alembic.exe revision -m "alert signal_name"`
Then edit the generated file's `upgrade()`/`downgrade()` (SQLite needs batch mode):

```python
def upgrade() -> None:
    with op.batch_alter_table("alerts") as b:
        b.add_column(sa.Column("signal_name", sa.String(length=64), nullable=True))
        b.create_index("ix_alerts_signal_name", ["signal_name"])

def downgrade() -> None:
    with op.batch_alter_table("alerts") as b:
        b.drop_index("ix_alerts_signal_name")
        b.drop_column("signal_name")
```

- [ ] **Step 5: Apply migration + run test**

Run: `cd backend && ./.venv/Scripts/alembic.exe upgrade head && ./.venv/Scripts/python.exe -m pytest tests/test_signal_alert_column.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/alert.py backend/alembic/versions/ backend/tests/test_signal_alert_column.py
git commit -m "feat(signals): Alert.signal_name column for engine-produced alerts"
```

---

### Task 2: Event model + extractors

**Files:**
- Create: `backend/app/signals/__init__.py` (empty)
- Create: `backend/app/signals/events.py`
- Test: `backend/tests/signals/test_events.py` (+ `backend/tests/signals/__init__.py`)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/signals/test_events.py
import pandas as pd
from app.signals.events import Event, extract_breakout, extract_volume_spike


def _df(rows):
    # rows: list of (date, close, high, low, volume); open inferred = close
    return pd.DataFrame([
        {"date": d, "open": c, "high": h, "low": lo, "close": c, "volume": v}
        for (d, c, h, lo, v) in rows
    ])


def test_breakout_emits_bull_on_new_n_day_high():
    # 20 flat bars at 100, then a close at 110 (new high) on the last bar.
    rows = [(f"2026-04-{i:02d}", 100, 101, 99, 1_000) for i in range(1, 21)]
    rows.append(("2026-05-01", 110, 111, 109, 1_000))
    events = extract_breakout(_df(rows), lookback=20)
    assert any(e.type == "breakout" and e.direction == "bull"
               and e.date == "2026-05-01" for e in events)


def test_breakout_silent_when_no_new_high():
    rows = [(f"2026-04-{i:02d}", 100, 101, 99, 1_000) for i in range(1, 22)]
    assert extract_breakout(_df(rows), lookback=20) == []


def test_volume_spike_emits_with_ratio_magnitude():
    rows = [(f"2026-04-{i:02d}", 100, 101, 99, 1_000) for i in range(1, 21)]
    rows.append(("2026-05-01", 100, 101, 99, 3_000))  # 3x avg
    events = extract_volume_spike(_df(rows), avg_period=20, k=2.0)
    spike = [e for e in events if e.type == "volume_spike"]
    assert spike and spike[-1].date == "2026-05-01"
    assert spike[-1].magnitude is not None and spike[-1].magnitude >= 2.0
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_events.py -q`
Expected: FAIL — `ModuleNotFoundError: app.signals.events`.

- [ ] **Step 3: Implement `events.py`**

```python
# backend/app/signals/events.py
"""Dated technical events extracted from an OHLCV window.

An Event is a fact that happened ON a specific bar. Detectors consume
streams of these to recognise multi-step setups over time. Extractors scan
the recent window and may emit several events (one per qualifying bar)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Event:
    date: str                       # ISO YYYY-MM-DD — the bar it occurs on
    type: str                       # "breakout" | "volume_spike" | ...
    direction: str | None = None    # "bull" | "bear" | None
    magnitude: float | None = None  # normalised strength (ratio, % amplitude)
    payload: dict[str, Any] = field(default_factory=dict)


def _iso(v: Any) -> str:
    s = str(v)
    return s[:10]


def extract_breakout(ohlcv: pd.DataFrame, *, lookback: int = 20) -> list[Event]:
    """Emit a bull event when a bar's close exceeds the prior `lookback`-bar
    high (Donchian breakout), a bear event when it breaks the prior low.
    Compares against the window BEFORE each bar (shifted) to avoid look-ahead."""
    if len(ohlcv) < lookback + 1:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    high = ohlcv["high"].astype(float).reset_index(drop=True)
    low = ohlcv["low"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    prior_high = high.shift(1).rolling(lookback).max()
    prior_low = low.shift(1).rolling(lookback).min()
    out: list[Event] = []
    for i in range(lookback, len(close)):
        ph, pl = prior_high.iloc[i], prior_low.iloc[i]
        if pd.notna(ph) and close.iloc[i] > ph:
            out.append(Event(_iso(dates.iloc[i]), "breakout", "bull",
                             magnitude=float((close.iloc[i] - ph) / ph) if ph else None,
                             payload={"level": float(ph), "lookback": lookback}))
        elif pd.notna(pl) and close.iloc[i] < pl:
            out.append(Event(_iso(dates.iloc[i]), "breakout", "bear",
                             magnitude=float((pl - close.iloc[i]) / pl) if pl else None,
                             payload={"level": float(pl), "lookback": lookback}))
    return out


def extract_volume_spike(
    ohlcv: pd.DataFrame, *, avg_period: int = 20, k: float = 2.0,
) -> list[Event]:
    """Emit an event on each bar whose volume ≥ k × its trailing avg."""
    if len(ohlcv) < avg_period + 1:
        return []
    vol = ohlcv["volume"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    avg = vol.shift(1).rolling(avg_period).mean()
    out: list[Event] = []
    for i in range(avg_period, len(vol)):
        a = avg.iloc[i]
        if pd.notna(a) and a > 0 and vol.iloc[i] >= k * a:
            out.append(Event(_iso(dates.iloc[i]), "volume_spike", None,
                             magnitude=float(vol.iloc[i] / a),
                             payload={"avg_period": avg_period}))
    return out


# Registry of active extractors for Phase 1a. Each is f(ohlcv) -> list[Event].
EXTRACTORS = [
    lambda df: extract_breakout(df, lookback=20),
    lambda df: extract_volume_spike(df, avg_period=20, k=2.0),
]


def extract_events(ohlcv: pd.DataFrame) -> list[Event]:
    """Run all extractors; return events sorted by date ascending."""
    events: list[Event] = []
    for fn in EXTRACTORS:
        try:
            events.extend(fn(ohlcv))
        except Exception:  # noqa: BLE001 — one bad extractor must not kill the rest
            continue
    return sorted(events, key=lambda e: e.date)
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_events.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/__init__.py backend/app/signals/events.py backend/tests/signals/
git commit -m "feat(signals): Event model + breakout/volume extractors"
```

---

### Task 3: SignalContext

**Files:**
- Create: `backend/app/signals/context.py`
- Test: `backend/tests/signals/test_context.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_context.py
import pandas as pd
from app.signals.context import build_context


def test_context_reports_uptrend_and_atr():
    rows = [{"date": f"2026-01-{i:02d}", "open": 100 + i, "high": 101 + i,
             "low": 99 + i, "close": 100 + i, "volume": 1000} for i in range(1, 31)]
    ctx = build_context(pd.DataFrame(rows))
    assert ctx.trend_sign == 1          # rising series → up
    assert ctx.atr is not None and ctx.atr > 0
    assert ctx.last_close == 130.0
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_context.py -q`
Expected: FAIL — `ModuleNotFoundError: app.signals.context`.

- [ ] **Step 3: Implement `context.py`**

```python
# backend/app/signals/context.py
"""Per-ticker features computed once and shared across detectors."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.indicators.atr import atr
from app.indicators.ema import ema


@dataclass(frozen=True)
class SignalContext:
    last_close: float
    trend_sign: int        # +1 up / -1 down / 0 flat (EMA200 slope, fallback EMA50)
    atr: float | None      # ATR(14) at last bar — normalises amplitudes/stops


def build_context(ohlcv: pd.DataFrame) -> SignalContext:
    close = ohlcv["close"].astype(float)
    last_close = float(close.iloc[-1])
    period = 200 if len(close) >= 200 else max(20, len(close) // 2)
    e = ema(close, period)
    if len(e) >= 6 and pd.notna(e.iloc[-1]) and pd.notna(e.iloc[-6]):
        slope = e.iloc[-1] - e.iloc[-6]
        trend_sign = 1 if slope > 0 else (-1 if slope < 0 else 0)
    else:
        trend_sign = 0
    a = atr(ohlcv, 14)
    atr_val = float(a.iloc[-1]) if len(a) and pd.notna(a.iloc[-1]) else None
    return SignalContext(last_close=last_close, trend_sign=trend_sign, atr=atr_val)
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_context.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/context.py backend/tests/signals/test_context.py
git commit -m "feat(signals): SignalContext (trend sign + ATR)"
```

---

### Task 4: Detector base — Protocol, SignalMatch, sequence helper

**Files:**
- Create: `backend/app/signals/detectors/__init__.py` (empty)
- Create: `backend/app/signals/detectors/base.py`
- Test: `backend/tests/signals/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_base.py
from app.signals.events import Event
from app.signals.detectors.base import find_after, SignalMatch


def test_find_after_respects_order_and_window():
    evs = [
        Event("2026-05-01", "breakout", "bull"),
        Event("2026-05-02", "volume_spike", None),
        Event("2026-05-10", "volume_spike", None),
    ]
    # volume spike within 3 bars of the breakout date → the 05-02 one
    hit = find_after(evs, "volume_spike", after="2026-05-01", within_days=3)
    assert hit is not None and hit.date == "2026-05-02"
    # nothing within 1 day
    assert find_after(evs, "volume_spike", after="2026-05-01", within_days=0) is None


def test_signalmatch_is_constructible():
    m = SignalMatch(name="x", tone="bull", confidence=70, signal_date="2026-05-02",
                    chain=[{"date": "2026-05-01", "label": "Breakout", "detail": ""}],
                    invalidation=None, factors={"f": 1.0})
    assert m.confidence == 70
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_base.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `base.py`**

```python
# backend/app/signals/detectors/base.py
"""Detector contract + SignalMatch + temporal-sequence helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any, Protocol

import pandas as pd

from app.signals.context import SignalContext
from app.signals.events import Event


@dataclass(frozen=True)
class SignalMatch:
    name: str
    tone: str                       # "bull" | "bear"
    confidence: int                 # 0..100
    signal_date: str                # ISO — date of the chain's last event
    chain: list[dict]               # [{date, label, detail}]
    invalidation: dict | None       # {"level": float, "reason": str}
    factors: dict[str, float] = field(default_factory=dict)


class SignalDetector(Protocol):
    name: str
    tone: str
    sources: list[str]
    min_bars: int
    def detect(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext,
    ) -> SignalMatch | None: ...


def _d(iso: str) -> _date:
    return _date.fromisoformat(iso[:10])


def find_after(
    events: list[Event], type_: str, *, after: str, within_days: int,
    direction: str | None = None,
) -> Event | None:
    """First event of `type_` (and optional `direction`) strictly after
    `after` and within `within_days` calendar days. Events assumed
    date-sorted ascending."""
    a = _d(after)
    for e in events:
        if e.type != type_:
            continue
        if direction is not None and e.direction != direction:
            continue
        ed = _d(e.date)
        if ed <= a:
            continue
        if (ed - a).days <= within_days:
            return e
    return None


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score(factors: dict[str, float], weights: dict[str, float]) -> int:
    """Weighted mean of [0,1] factors → 0..100 int."""
    num = sum(clamp01(factors.get(k, 0.0)) * w for k, w in weights.items())
    den = sum(weights.values()) or 1.0
    return round(100.0 * num / den)
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_base.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/detectors/__init__.py backend/app/signals/detectors/base.py backend/tests/signals/test_base.py
git commit -m "feat(signals): detector Protocol, SignalMatch, sequence helpers"
```

---

### Task 5: Volume-Confirmed Breakout detector + registry

**Files:**
- Create: `backend/app/signals/detectors/volume_breakout.py`
- Create: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_volume_breakout.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_volume_breakout.py
import pandas as pd
from app.signals.context import build_context
from app.signals.events import extract_events
from app.signals.detectors.volume_breakout import VolumeBreakout


def _series(breakout=True, with_volume=True):
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    if breakout:
        rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                     "close": 110, "volume": 4000 if with_volume else 1000})
    return pd.DataFrame(rows)


def test_fires_when_breakout_confirmed_by_volume():
    df = _series(breakout=True, with_volume=True)
    m = VolumeBreakout().detect(extract_events(df), df, build_context(df))
    assert m is not None and m.tone == "bull" and m.confidence > 0
    assert any(s["label"].lower().startswith("breakout") for s in m.chain)
    assert any("volume" in s["label"].lower() for s in m.chain)


def test_silent_without_volume_confirmation():
    df = _series(breakout=True, with_volume=False)
    assert VolumeBreakout().detect(extract_events(df), df, build_context(df)) is None


def test_silent_without_breakout():
    df = _series(breakout=False)
    assert VolumeBreakout().detect(extract_events(df), df, build_context(df)) is None
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_volume_breakout.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the detector + registry**

```python
# backend/app/signals/detectors/volume_breakout.py
"""Volume-Confirmed Breakout: a Donchian breakout corroborated by a volume
spike within a few bars. Source: Donchian channel breakout + volume
confirmation (Granville OBV lineage)."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

_CONFIRM_WINDOW_DAYS = 4


class VolumeBreakout:
    name = "volume_breakout"
    tone = "bull"  # default; emits bull or bear per the breakout direction
    sources = ["Donchian channel breakout + volume confirmation (OBV lineage)"]
    min_bars = 25

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        # Most-recent breakout event.
        breakouts = [e for e in events if e.type == "breakout"]
        if not breakouts:
            return None
        bo = breakouts[-1]
        # Require a volume spike on/after the breakout, within the window.
        vol = find_after(events, "volume_spike", after=bo.date, within_days=_CONFIRM_WINDOW_DAYS)
        # Also accept a spike ON the breakout bar itself.
        same_bar = any(e.type == "volume_spike" and e.date == bo.date for e in events)
        if vol is None and not same_bar:
            return None
        vol_mag = (vol.magnitude if vol else
                   next((e.magnitude for e in events
                         if e.type == "volume_spike" and e.date == bo.date), None)) or 0.0

        tone = bo.direction or "bull"
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "breakout_strength": clamp01((bo.magnitude or 0.0) / 0.05),   # 5% over level = full
            "volume_strength": clamp01((vol_mag - 1.0) / 2.0),            # 3x avg = full
            "trend_alignment": 1.0 if trend_aligned else 0.4,
        }
        conf = score(factors, {"breakout_strength": 1.0, "volume_strength": 1.2, "trend_alignment": 0.8})
        confirm_date = vol.date if vol else bo.date
        chain = [
            {"date": bo.date, "label": f"Breakout {tone}",
             "detail": f"chiusura oltre il livello {bo.payload.get('level')}"},
            {"date": confirm_date, "label": "Conferma volume",
             "detail": f"{vol_mag:.1f}× la media a 20 sedute"},
        ]
        invalidation = (
            {"level": float(bo.payload.get("level")),
             "reason": "rientro sotto il livello di breakout"}
            if bo.payload.get("level") is not None else None
        )
        return SignalMatch(
            name=self.name, tone=tone, confidence=conf, signal_date=confirm_date,
            chain=chain, invalidation=invalidation, factors=factors,
        )
```

```python
# backend/app/signals/detectors/registry.py
"""Active signal detectors for the current phase."""
from app.signals.detectors.volume_breakout import VolumeBreakout

DETECTORS = [VolumeBreakout()]
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_volume_breakout.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/detectors/volume_breakout.py backend/app/signals/detectors/registry.py backend/tests/signals/test_volume_breakout.py
git commit -m "feat(signals): Volume-Confirmed Breakout detector"
```

---

### Task 6: Runner — detect_signals(ohlcv)

**Files:**
- Create: `backend/app/signals/runner.py`
- Test: `backend/tests/signals/test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_runner.py
import pandas as pd
from app.signals.runner import detect_signals


def test_runner_returns_match_for_confirmed_breakout():
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    matches = detect_signals(pd.DataFrame(rows))
    assert any(m.name == "volume_breakout" for m in matches)


def test_runner_isolates_a_failing_detector(monkeypatch):
    class Boom:
        name = "boom"; min_bars = 1
        def detect(self, *a, **k): raise RuntimeError("nope")
    monkeypatch.setattr("app.signals.runner.DETECTORS", [Boom()])
    # Must not raise; just returns no matches.
    assert detect_signals(pd.DataFrame([{"date": "2026-05-01", "open": 1,
        "high": 1, "low": 1, "close": 1, "volume": 1}])) == []
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_runner.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `runner.py`**

```python
# backend/app/signals/runner.py
"""Run all active detectors over one ticker's OHLCV → list[SignalMatch]."""
from __future__ import annotations

import pandas as pd
from loguru import logger

from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.registry import DETECTORS
from app.signals.events import extract_events


def detect_signals(ohlcv: pd.DataFrame) -> list[SignalMatch]:
    if ohlcv is None or len(ohlcv) < 2:
        return []
    try:
        events = extract_events(ohlcv)
        ctx = build_context(ohlcv)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[signals] feature build failed: {e}")
        return []
    out: list[SignalMatch] = []
    for det in DETECTORS:
        try:
            m = det.detect(events, ohlcv, ctx)
            if m is not None:
                out.append(m)
        except Exception as e:  # noqa: BLE001 — one detector must not kill the rest
            logger.warning(f"[signals] detector {getattr(det, 'name', '?')} crashed: {e}")
    return out
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/runner.py backend/tests/signals/test_runner.py
git commit -m "feat(signals): runner with per-detector isolation"
```

---

### Task 7: signal_scan_service — SignalMatch → Alert with dedup

**Files:**
- Create: `backend/app/signals/signal_scan_service.py`
- Modify: `backend/app/core/config.py` (add `signal_min_confidence: int = 60`)
- Test: `backend/tests/signals/test_signal_scan_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/signals/test_signal_scan_service.py
from datetime import date
import pandas as pd
from app.models import Alert, Stock
from app.signals.signal_scan_service import evaluate_signals


def _confirmed_df():
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    return pd.DataFrame(rows)


def test_creates_signal_alert_above_threshold(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    s = Stock(ticker="BRK_SIG", exchange="NASDAQ", name="BO Co", country="US")
    db.add(s); db.flush()
    n = evaluate_signals(db, s, _confirmed_df())
    db.commit()
    assert n == 1
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    assert a is not None and a.rule_id is None and a.signal_date == date(2026, 5, 1)


def test_dedup_same_signal_date(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    s = Stock(ticker="BRK_SIG2", exchange="NASDAQ", name="BO2", country="US")
    db.add(s); db.flush()
    df = _confirmed_df()
    assert evaluate_signals(db, s, df) == 1
    db.commit()
    assert evaluate_signals(db, s, df) == 0   # same (stock, name, signal_date) → skip
    db.commit()


def test_below_threshold_not_emitted(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 99)
    s = Stock(ticker="BRK_SIG3", exchange="NASDAQ", name="BO3", country="US")
    db.add(s); db.flush()
    assert evaluate_signals(db, s, _confirmed_df()) == 0
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_signal_scan_service.py -q`
Expected: FAIL — `ModuleNotFoundError` (and `AttributeError` on settings until Step 3).

- [ ] **Step 3: Add the setting + implement the service**

In `backend/app/core/config.py`, add to the Settings class (near the other ints):

```python
    # Signal engine: minimum confidence (0-100) for a detected signal to
    # become an alert. Below this the signal is computed but not surfaced.
    signal_min_confidence: int = 60
```

```python
# backend/app/signals/signal_scan_service.py
"""Turn detected signals into deduped Alert rows during the scan."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Stock
from app.signals.runner import detect_signals


def _to_date(iso: str) -> date | None:
    try:
        return date.fromisoformat(iso[:10])
    except (ValueError, TypeError):
        return None


def evaluate_signals(db: Session, stock: Stock, ohlcv: pd.DataFrame) -> int:
    """Detect signals for `stock` and add Alert rows for new ones above the
    confidence threshold. Returns the count added. Caller commits."""
    last_close = float(ohlcv["close"].iloc[-1])
    added = 0
    for m in detect_signals(ohlcv):
        if m.confidence < settings.signal_min_confidence:
            continue
        sig_date = _to_date(m.signal_date)
        # Dedup: same (stock, signal, signal_date) already emitted → skip.
        exists = db.execute(
            select(Alert.id).where(
                Alert.stock_id == stock.id,
                Alert.signal_name == m.name,
                Alert.signal_date == sig_date,
            ).limit(1)
        ).scalars().first()
        if exists is not None:
            continue
        snapshot = {
            "tone": m.tone, "confidence": m.confidence, "chain": m.chain,
            "factors": m.factors, "invalidation": m.invalidation,
            "sources": getattr(_detector_for(m.name), "sources", []),
        }
        db.add(Alert(
            rule_id=None, stock_id=stock.id, trigger_price=last_close,
            signal_date=sig_date, signal_name=m.name,
            snapshot=json.dumps(snapshot),
        ))
        added += 1
    return added


def _detector_for(name: str):
    from app.signals.detectors.registry import DETECTORS
    return next((d for d in DETECTORS if getattr(d, "name", None) == name), None)
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_signal_scan_service.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals/signal_scan_service.py backend/app/core/config.py backend/tests/signals/test_signal_scan_service.py
git commit -m "feat(signals): signal_scan_service (SignalMatch -> deduped Alert)"
```

---

### Task 8: Hook into scan + derive rule_kind for the UI

**Files:**
- Modify: `backend/app/services/scan_service.py` (inside `scan_universe`, after the per-rule loop, still inside the `for stock` loop)
- Modify: the place that builds `AlertOut.rule_kind` (search: `grep -rn "rule_kind" backend/app/services/alert_service.py backend/app/schemas/alert.py backend/app/api/alerts.py`)
- Test: `backend/tests/test_scan_emits_signal_alerts.py`

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/test_scan_emits_signal_alerts.py
import pandas as pd
from datetime import date
from app.models import Alert, OhlcvDaily, Stock
from app.services import scan_service


def _seed_breakout_stock(db):
    s = Stock(ticker="SCAN_BO", exchange="NASDAQ", name="Scan BO", country="US")
    db.add(s); db.flush()
    for i in range(1, 21):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 4, i),
                          open=100, high=101, low=99, close=100, volume=1000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 1),
                      open=100, high=112, low=100, close=110, volume=4000))
    db.commit()
    return s


def test_scan_creates_signal_alert(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    s = _seed_breakout_stock(db)
    scan_service.scan_universe(db)
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    assert a is not None
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_scan_emits_signal_alerts.py -q`
Expected: FAIL — no signal alert (hook not wired).

- [ ] **Step 3: Wire the signals sub-phase into `scan_universe`**

In `backend/app/services/scan_service.py`, add the import near the top:

```python
from app.signals.signal_scan_service import evaluate_signals
```

Inside `scan_universe`, within the `for idx, stock in enumerate(...)` loop, AFTER the `for kind, candidate_global in global_rules.items():` block finishes (same indent as that `for`), add:

```python
            # Signal engine — runs on the same OHLCV already loaded. Wrapped
            # so a signals failure can never abort the legacy rule scan.
            try:
                fired = evaluate_signals(db, stock, ohlcv)
                result.alerts_fired += fired
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[scan] signals failed for {stock.ticker}: {e}")
```

(The existing `db.commit()` / state persistence at the loop tail covers the new Alert rows.)

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_scan_emits_signal_alerts.py -q`
Expected: PASS.

- [ ] **Step 5: Derive `rule_kind` for signal alerts**

Find where `AlertOut.rule_kind` is populated:
`grep -rn "rule_kind" backend/app/services/alert_service.py backend/app/schemas/alert.py backend/app/api/alerts.py`

At that site, the kind is currently taken from the joined `Rule`. Change it to fall back to the signal name when there's no rule:

```python
# where `alert` is the ORM row and `rule` may be None:
rule_kind = rule.kind if rule is not None else (
    f"signal:{alert.signal_name}" if alert.signal_name else "unknown"
)
```

Add a test asserting an alert with `signal_name="volume_breakout"` serialises with `rule_kind == "signal:volume_breakout"` in the same test file.

- [ ] **Step 6: Full suite + commit**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all green (594 prior + new).

```bash
git add backend/app/services/scan_service.py backend/tests/test_scan_emits_signal_alerts.py <the rule_kind file>
git commit -m "feat(signals): wire signal engine into scan + signal:<name> kind"
```

---

## Follow-up (separate plans, additive)

- **Plan 1b — remaining detectors:** RSI divergence, trend-pullback, squeeze expansion, 52w-high momentum (+ their extractors: `rsi_divergence`, `ema_cross`, `bb_squeeze`/`bb_expansion`). Each is one task pair (extractor + detector) on this scaffolding.
- **Plan 1c — enriched alert UI:** render the `chain` timeline + confidence badge + tone + invalidation + cited `sources` for `rule_kind` starting `signal:` in the alert feed/detail components.
- **Phase 2 / 3** per the design spec.

## Self-review notes
- Spec coverage: event layer (T2), context (T3), detector contract + sequence (T4), one grounded detector (T5), runner isolation (T6), alert integration + dedup + threshold (T7), scan hook + UI kind (T8). UI rendering + the other 4 detectors are explicitly deferred to 1b/1c. ✓
- No placeholders: every code step has real code; the only "search for the site" step (T8.5) is a grep with the exact edit shown. ✓
- Type consistency: `Event`, `SignalMatch`, `SignalContext`, `detect_signals`, `evaluate_signals`, `find_after`, `score`, `signal_min_confidence`, `Alert.signal_name` are used consistently across tasks. ✓
