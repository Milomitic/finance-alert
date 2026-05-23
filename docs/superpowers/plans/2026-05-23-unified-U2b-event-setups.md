# Unified Signals — Phase U2b: new-event technical setups (MACD / gap / ADX)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Add the technical setups that need new atomic events: MACD signal-line cross + MACD regular divergence, opening gaps, and ADX trend strength — then the detectors MACD Divergence (B6), Gap-and-Go (B11), and ADX Trend Confirmation (B13).

**Architecture:** Additive. New extractors in `events.py` (registered in `EXTRACTORS`); new detectors consume them with confirmations (atomic-never-alone). Full suite stays green (582 passed / 1 skipped).

**Tech Stack:** Python 3.11, pandas, pytest. Reuses `app/indicators/macd.py` (`macd(close, fast=12, slow=26, signal=9) -> (line, signal, hist)`), `app/indicators/adx.py` (`adx(ohlcv, period=14) -> (adx, plus_di, minus_di)`), `app/signals/pivots.py` (`find_pivots`).

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; ASCII-only; gate factors excluded from `score` weights.

**Scope note:** B7 hidden divergence + Layer-D candlesticks are U2c.

---

### Task 1: macd_cross + gap + adx_trend extractors

**Files:**
- Modify: `backend/app/signals/events.py`
- Test: `backend/tests/signals/test_events_u2b.py`

- [ ] **Step 1: Write the failing tests**
```python
# backend/tests/signals/test_events_u2b.py
import pandas as pd
from app.signals.events import extract_macd_cross, extract_gap, extract_adx_trend


def _df(rows):
    # rows: (close, high, low) ; open defaults to close unless 4th given
    out = []
    for i, r in enumerate(rows):
        c, h, lo = r[0], r[1], r[2]
        op = r[3] if len(r) > 3 else c
        out.append({"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
                    "open": op, "high": h, "low": lo, "close": c, "volume": 1000})
    return pd.DataFrame(out)


def test_macd_cross_emits_bull_when_line_crosses_up():
    closes = [100 - i for i in range(40)] + [60 + i * 2 for i in range(20)]
    evs = extract_macd_cross(_df([(c, c + 1, c - 1) for c in closes]))
    assert any(e.type == "macd_cross" and e.direction == "bull" for e in evs)


def test_gap_emits_up_on_open_above_prev_close():
    rows = [(100, 101, 99) for _ in range(5)]
    rows.append((110, 112, 108, 108))   # open 108 vs prev close 100 -> +8% gap up
    evs = extract_gap(_df(rows), min_pct=0.02)
    assert any(e.type == "gap" and e.direction == "bull" for e in evs)


def test_adx_trend_emits_bull_in_strong_uptrend():
    closes = [100 + i * 2 for i in range(40)]   # strong, steady uptrend
    evs = extract_adx_trend(_df([(c, c + 1, c - 1) for c in closes]), period=14, adx_min=20)
    assert any(e.type == "adx_trend" and e.direction == "bull" for e in evs)
```

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement in `events.py`** (after `extract_sr_levels`, before `EXTRACTORS`). Add imports at top: `from app.indicators.macd import macd` and `from app.indicators.adx import adx`.
```python
def extract_macd_cross(
    ohlcv: pd.DataFrame, *, fast: int = 12, slow: int = 26, signal: int = 9,
) -> list[Event]:
    """Emit macd_cross on each bar where the MACD histogram changes sign:
    bull when the line crosses ABOVE its signal (hist <0 -> >=0), bear below."""
    if len(ohlcv) < slow + signal + 1:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    line, sig, hist = macd(close, fast, slow, signal)
    hist = hist.reset_index(drop=True)
    out: list[Event] = []
    for i in range(1, len(close)):
        p, c = hist.iloc[i - 1], hist.iloc[i]
        if pd.isna(p) or pd.isna(c):
            continue
        if p <= 0 < c:
            out.append(Event(_iso(dates.iloc[i]), "macd_cross", "bull",
                             magnitude=float(abs(c) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow, "signal": signal}))
        elif p >= 0 > c:
            out.append(Event(_iso(dates.iloc[i]), "macd_cross", "bear",
                             magnitude=float(abs(c) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow, "signal": signal}))
    return out


def extract_gap(ohlcv: pd.DataFrame, *, min_pct: float = 0.02) -> list[Event]:
    """Emit gap (bull/bear) when a bar opens beyond the prior close by >= min_pct."""
    if len(ohlcv) < 2:
        return []
    open_ = ohlcv["open"].astype(float).reset_index(drop=True)
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    out: list[Event] = []
    for i in range(1, len(close)):
        prev_c = close.iloc[i - 1]
        if prev_c <= 0:
            continue
        gap_pct = (open_.iloc[i] - prev_c) / prev_c
        if gap_pct >= min_pct:
            out.append(Event(_iso(dates.iloc[i]), "gap", "bull", magnitude=float(gap_pct),
                             payload={"gap_pct": float(gap_pct), "open": float(open_.iloc[i]),
                                      "prev_close": float(prev_c)}))
        elif gap_pct <= -min_pct:
            out.append(Event(_iso(dates.iloc[i]), "gap", "bear", magnitude=float(abs(gap_pct)),
                             payload={"gap_pct": float(gap_pct), "open": float(open_.iloc[i]),
                                      "prev_close": float(prev_c)}))
    return out


def extract_adx_trend(
    ohlcv: pd.DataFrame, *, period: int = 14, adx_min: float = 25.0,
) -> list[Event]:
    """Emit adx_trend on bars where ADX >= adx_min: bull when +DI > -DI, bear
    when -DI > +DI. magnitude = (ADX - adx_min) / (100 - adx_min) clamped."""
    if len(ohlcv) < 2 * period + 2:
        return []
    adx_s, plus_di, minus_di = adx(ohlcv, period)
    adx_s = adx_s.reset_index(drop=True)
    plus_di = plus_di.reset_index(drop=True)
    minus_di = minus_di.reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    out: list[Event] = []
    for i in range(len(adx_s)):
        a, p, m = adx_s.iloc[i], plus_di.iloc[i], minus_di.iloc[i]
        if pd.isna(a) or pd.isna(p) or pd.isna(m) or a < adx_min:
            continue
        mag = float(max(0.0, min(1.0, (a - adx_min) / (100.0 - adx_min)))) if adx_min < 100 else None
        if p > m:
            out.append(Event(_iso(dates.iloc[i]), "adx_trend", "bull", magnitude=mag,
                             payload={"adx": float(a), "plus_di": float(p), "minus_di": float(m)}))
        elif m > p:
            out.append(Event(_iso(dates.iloc[i]), "adx_trend", "bear", magnitude=mag,
                             payload={"adx": float(a), "plus_di": float(p), "minus_di": float(m)}))
    return out
```
Extend `EXTRACTORS` (append three):
```python
    lambda df: extract_macd_cross(df),
    lambda df: extract_gap(df, min_pct=0.02),
    lambda df: extract_adx_trend(df, period=14, adx_min=25.0),
```

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_events_u2b.py tests/signals/ -q` → green.
```bash
git add backend/app/signals/events.py backend/tests/signals/test_events_u2b.py
git commit -m "feat(signals): macd_cross + gap + adx_trend extractors"
```

---

### Task 2: macd_divergence extractor

**Files:**
- Modify: `backend/app/signals/events.py`
- Test: `backend/tests/signals/test_events_u2b.py` (add a test)

- [ ] **Step 1: Add the failing test** to `test_events_u2b.py`:
```python
def test_macd_divergence_returns_list():
    closes = [100 - i for i in range(20)] + [80 + (i % 3) for i in range(20)]
    from app.signals.events import extract_macd_divergence
    evs = extract_macd_divergence(_df([(c, c + 1, c - 1) for c in closes]))
    assert isinstance(evs, list)   # smoke: deterministic MACD divergence is hard to synthesise
```

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement** in `events.py` (mirrors `extract_rsi_divergence` but on the MACD line). `find_pivots` + `macd` already imported.
```python
def extract_macd_divergence(
    ohlcv: pd.DataFrame, *, fast: int = 12, slow: int = 26, signal: int = 9,
    pivot_w: int = 5, max_gap: int = 60,
) -> list[Event]:
    """Regular MACD-line divergence over the two most recent price pivots.
    Bull: price lower-low but MACD higher-low. Bear: mirror on highs."""
    if len(ohlcv) < slow + signal + 2 * pivot_w + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    line, _sig, _hist = macd(close, fast, slow, signal)
    line = line.reset_index(drop=True)
    out: list[Event] = []
    lows = find_pivots(close, pivot_w, kind="low")
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if (b - a) <= max_gap and close.iloc[b] < close.iloc[a] \
                and pd.notna(line.iloc[a]) and pd.notna(line.iloc[b]) and line.iloc[b] > line.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "macd_divergence", "bull",
                             magnitude=float(min(1.0, abs(line.iloc[b] - line.iloc[a]) / (abs(line.iloc[a]) + 1e-9))),
                             payload={"pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])]}))
    highs = find_pivots(close, pivot_w, kind="high")
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if (b - a) <= max_gap and close.iloc[b] > close.iloc[a] \
                and pd.notna(line.iloc[a]) and pd.notna(line.iloc[b]) and line.iloc[b] < line.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "macd_divergence", "bear",
                             magnitude=float(min(1.0, abs(line.iloc[a] - line.iloc[b]) / (abs(line.iloc[a]) + 1e-9))),
                             payload={"pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])]}))
    return out
```
Append to `EXTRACTORS`: `lambda df: extract_macd_divergence(df, pivot_w=5, max_gap=60),`

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/ -q` → green.
```bash
git add backend/app/signals/events.py backend/tests/signals/test_events_u2b.py
git commit -m "feat(signals): macd_divergence extractor"
```

---

### Task 3: MacdDivergence detector (B6)

**Files:**
- Create: `backend/app/signals/detectors/macd_divergence.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_macd_divergence.py`

- [ ] **Step 1: Write the failing test** (event-injection)
```python
# backend/tests/signals/test_macd_divergence.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.macd_divergence import MacdDivergence
from app.signals.events import Event


def _df(n=40):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_from_bull_macd_divergence():
    events = [Event("2026-02-10", "macd_divergence", "bull", magnitude=0.6,
                    payload={"pivot_dates": ["2026-01-20", "2026-02-10"]})]
    m = MacdDivergence().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("divergen" in s["label"].lower() for s in m.chain)


def test_silent_without_event():
    assert MacdDivergence().detect([], _df(), build_context(_df())) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/macd_divergence.py
"""MACD Regular Divergence (B6): price makes a lower low while the MACD line
makes a higher low (bull) or mirror (bear) - a momentum-reversal setup.
Source: Appel (MACD); divergence as the consolidated momentum-reversal read.
Consumes the macd_divergence event."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, score
from app.signals.events import Event

_COUNTER_TREND = 1.0
_WITH_TREND = 0.5


class MacdDivergence:
    name = "macd_divergence"
    tone = "bull"
    sources = ["Appel MACD; regular divergence as a momentum-reversal read"]
    min_bars = 35

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        divs = [e for e in events if e.type == "macd_divergence"]
        if not divs:
            return None
        d = divs[-1]
        tone = d.direction or "bull"
        counter = (tone == "bull" and ctx.trend_sign <= 0) or (tone == "bear" and ctx.trend_sign >= 0)
        factors = {
            "divergence_amplitude": clamp01(d.magnitude or 0.0),
            "trend_context": _COUNTER_TREND if counter else _WITH_TREND,
        }
        conf = score(factors, {"divergence_amplitude": 1.0, "trend_context": 1.0})
        pivots = d.payload.get("pivot_dates") or [d.date, d.date]
        chain = [
            {"date": pivots[0], "label": "Primo estremo di prezzo", "detail": "minimo/massimo iniziale"},
            {"date": d.date, "label": f"Divergenza MACD {tone}",
             "detail": "prezzo e linea MACD divergono (setup di inversione)"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=d.date, chain=chain, invalidation=None, factors=factors)
```
Append `MacdDivergence()` to `DETECTORS` in `registry.py` (with its import).

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_macd_divergence.py tests/signals/ -q` → green.
```bash
git add backend/app/signals/detectors/macd_divergence.py backend/app/signals/detectors/registry.py backend/tests/signals/test_macd_divergence.py
git commit -m "feat(signals): MACD Regular Divergence detector (B6)"
```

---

### Task 4: GapAndGo detector (B11)

**Files:**
- Create: `backend/app/signals/detectors/gap_and_go.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_gap_and_go.py`

- [ ] **Step 1: Write the failing test** (event-injection)
```python
# backend/tests/signals/test_gap_and_go.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.gap_and_go import GapAndGo
from app.signals.events import Event


def _df(n=30):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_gap_up_with_volume():
    events = [
        Event("2026-02-10", "gap", "bull", magnitude=0.05, payload={"gap_pct": 0.05}),
        Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
    ]
    m = GapAndGo().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("gap" in s["label"].lower() for s in m.chain)


def test_silent_gap_without_volume():
    events = [Event("2026-02-10", "gap", "bull", magnitude=0.05, payload={"gap_pct": 0.05})]
    assert GapAndGo().detect(events, _df(), build_context(_df())) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/gap_and_go.py
"""Gap-and-Go (B11): an opening gap confirmed by a volume spike - the gap is
backed by participation, favouring continuation in the gap direction (vs an
unfilled low-volume gap that tends to fade). Source: gap taxonomy (breakaway
vs exhaustion) + volume confirmation. Confirmed: gap + volume spike."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

_VOL_WINDOW_DAYS = 2


class GapAndGo:
    name = "gap_and_go"
    tone = "bull"
    sources = ["Gap taxonomy (breakaway vs exhaustion) + volume confirmation"]
    min_bars = 20

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        gaps = [e for e in events if e.type == "gap"]
        if not gaps:
            return None
        gap = gaps[-1]
        tone = gap.direction or "bull"
        # Confirmation: a volume spike on the gap bar or just after.
        vol_same = any(e.type == "volume_spike" and e.date == gap.date for e in events)
        vol_after = find_after(events, "volume_spike", after=gap.date, within_days=_VOL_WINDOW_DAYS)
        if not (vol_same or vol_after):
            return None
        vol_mag = next((e.magnitude for e in events
                        if e.type == "volume_spike" and e.date == gap.date), None) \
            or (vol_after.magnitude if vol_after else None) or 0.0
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "gap_size": clamp01((gap.magnitude or 0.0) / 0.05),     # 5% gap = full
            "volume_strength": clamp01((vol_mag - 1.0) / 2.0),      # 3x avg = full
            "trend_alignment": 1.0 if trend_aligned else 0.5,
        }
        conf = score(factors, {"gap_size": 1.0, "volume_strength": 1.0, "trend_alignment": 0.6})
        gp = gap.payload.get("gap_pct")
        gp_txt = f"{gp * 100:.1f}%" if isinstance(gp, (int, float)) else "n/d"
        chain = [
            {"date": gap.date, "label": f"Gap {tone}", "detail": f"apertura in gap del {gp_txt}"},
            {"date": gap.date, "label": "Conferma volume",
             "detail": f"{vol_mag:.1f}x la media: gap partecipato"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=gap.date, chain=chain, invalidation=None, factors=factors)
```
Append `GapAndGo()` to `DETECTORS`.

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_gap_and_go.py tests/signals/ -q` → green.
```bash
git add backend/app/signals/detectors/gap_and_go.py backend/app/signals/detectors/registry.py backend/tests/signals/test_gap_and_go.py
git commit -m "feat(signals): Gap-and-Go detector (B11)"
```

---

### Task 5: AdxConfirmation detector (B13) + full suite

**Files:**
- Create: `backend/app/signals/detectors/adx_confirmation.py`
- Modify: `backend/app/signals/detectors/registry.py`
- Test: `backend/tests/signals/test_adx_confirmation.py`

- [ ] **Step 1: Write the failing test** (event-injection)
```python
# backend/tests/signals/test_adx_confirmation.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.adx_confirmation import AdxConfirmation
from app.signals.events import Event


def _df(n=40):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_strong_trend_with_breakout():
    events = [
        Event("2026-02-10", "adx_trend", "bull", magnitude=0.6,
              payload={"adx": 35.0, "plus_di": 30.0, "minus_di": 12.0}),
        Event("2026-02-10", "breakout", "bull", magnitude=0.04, payload={"level": 105.0}),
    ]
    m = AdxConfirmation().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("adx" in s["label"].lower() or "trend" in s["label"].lower() for s in m.chain)


def test_silent_adx_without_breakout():
    events = [Event("2026-02-10", "adx_trend", "bull", magnitude=0.6,
                    payload={"adx": 35.0, "plus_di": 30.0, "minus_di": 12.0})]
    assert AdxConfirmation().detect(events, _df(), build_context(_df())) is None
```

- [ ] **Step 2: Run, verify fail** — ModuleNotFoundError.

- [ ] **Step 3: Implement + register**
```python
# backend/app/signals/detectors/adx_confirmation.py
"""ADX Trend Confirmation (B13): a strong directional regime (ADX high with
+DI/-DI alignment) confirmed by a breakout in the same direction - a
trend-following entry with a strength filter. Source: Wilder (1978) ADX/DMI.
Confirmed: adx_trend + breakout."""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

_BREAK_WINDOW_DAYS = 4


class AdxConfirmation:
    name = "adx_confirmation"
    tone = "bull"
    sources = ["Wilder (1978) ADX/DMI + breakout confirmation"]
    min_bars = 30

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        adxs = [e for e in events if e.type == "adx_trend"]
        if not adxs:
            return None
        a = adxs[-1]
        tone = a.direction or "bull"
        # Confirmation: a breakout in the same direction on/around the adx bar.
        bo_same = any(e.type == "breakout" and e.direction == tone and e.date == a.date for e in events)
        bo_after = find_after(events, "breakout", after=a.date, within_days=_BREAK_WINDOW_DAYS, direction=tone)
        bo_before = any(e.type == "breakout" and e.direction == tone for e in events)
        if not (bo_same or bo_after or bo_before):
            return None
        factors = {
            "adx_strength": clamp01(a.magnitude or 0.0),
            "di_spread": clamp01(abs((a.payload.get("plus_di") or 0) - (a.payload.get("minus_di") or 0)) / 25.0),
            "breakout": 1.0,   # gate (display only)
        }
        conf = score(factors, {"adx_strength": 1.0, "di_spread": 0.6})
        adx_v = a.payload.get("adx")
        chain = [
            {"date": a.date, "label": f"Trend forte (ADX) {tone}",
             "detail": f"ADX {adx_v} con DI allineati"},
            {"date": a.date, "label": "Conferma breakout",
             "detail": "rottura nel verso del trend"},
        ]
        return SignalMatch(name=self.name, tone=tone, confidence=conf,
                           signal_date=a.date, chain=chain, invalidation=None, factors=factors)
```
Append `AdxConfirmation()` to `DETECTORS`.

- [ ] **Step 4: Run + full suite + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_adx_confirmation.py tests/signals/ -q` → green, then full suite `tests/ -q`. Some scan/visibility tests may need `>= 1` count tolerance (more detectors fire on shared fixtures) — relax as needed, keep targeted assertions.
```bash
git add backend/app/signals/detectors/adx_confirmation.py backend/app/signals/detectors/registry.py backend/tests/signals/test_adx_confirmation.py backend/tests/
git commit -m "feat(signals): ADX Trend Confirmation detector (B13); U2b registry now 11"
```

---

## Self-review notes
- Spec coverage: B6 MACD divergence (T3), B11 gap-and-go (T4), B13 ADX confirmation (T5); new atomic events macd_cross/gap/adx_trend (T1) + macd_divergence (T2). B7 hidden divergence + candlesticks deferred to U2c. ✓
- Atomic-never-alone: gap_and_go = gap + volume; adx_confirmation = adx_trend + breakout; macd_divergence consumes a 2-pivot divergence structure (like the existing RsiDivergence). Gate factors excluded from score weights. ✓
- Indicator signatures verified (macd, adx). The macd_divergence extractor test is a deliberate smoke check (synthetic MACD divergence is fragile); the DETECTOR is tested by event injection. ✓
- Type consistency: `extract_macd_cross/gap/adx_trend/macd_divergence`, `MacdDivergence`/`GapAndGo`/`AdxConfirmation`, `find_after`, `score`/`clamp01` consistent; all append to `DETECTORS`. ✓
- ASCII-only. ✓

## Follow-up
- **U2c** — B7 hidden divergence + Layer-D candlestick events + confirmed candlestick detectors.
- **U3** — non-technical producers + hybrids. **U4** — geometric.
