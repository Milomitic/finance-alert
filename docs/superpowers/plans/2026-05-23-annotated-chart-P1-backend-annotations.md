# Annotated Chart — Phase P1: detector annotations (backend)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Each signal carries a structured `annotations` block in its snapshot — `levels` (horizontal lines: neckline / breakout / support / resistance / stop) and `points` (pattern-shape vertices) — so the P2 SVG can draw the signal on the chart. Spec: `docs/superpowers/specs/2026-05-23-signal-annotated-chart-design.md`.

**Architecture:** Add `annotations` to `SignalMatch`; `signal_scan_service` auto-derives the `stop` level from the existing `invalidation` (so detectors don't repeat it) and serialises `annotations` into the snapshot. Detectors add their SPECIFIC levels/points. Markers stay frontend-derived from `chain[].date`. Additive — full suite stays green (642 passed / 1 skipped).

**Tech Stack:** Python/pandas/pytest; TS type only (no UI in P1).

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; ASCII-only.

**Annotations contract:**
```python
annotations = {
    "levels": [{"label": str, "price": float, "kind": str}],  # kind: neckline|breakout|support|resistance|stop
    "points": [{"date": "YYYY-MM-DD", "price": float}],        # ordered shape vertices; [] if none
}
```

---

### Task P1-T1: annotations infra (SignalMatch + auto-stop + snapshot + TS type)

**Files:**
- Modify: `backend/app/signals/detectors/base.py` (`SignalMatch`)
- Modify: `backend/app/signals/signal_scan_service.py` (snapshot build + auto-stop)
- Modify: `frontend/src/api/types.ts` (`SignalSnapshot`)
- Test: `backend/tests/signals/test_annotations.py`

- [ ] **Step 1: Write the failing test**
```python
# backend/tests/signals/test_annotations.py
import json, pandas as pd
from datetime import date
from app.models import Alert, Stock
from app.signals.signal_scan_service import evaluate_signals


def _confirmed_df():
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    return pd.DataFrame(rows)


def test_snapshot_carries_annotations_with_stop(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    s = Stock(ticker="ANN", exchange="NASDAQ", name="Ann", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_df()); db.commit()
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    assert a is not None
    snap = json.loads(a.snapshot)
    assert "annotations" in snap
    ann = snap["annotations"]
    assert isinstance(ann.get("levels"), list) and isinstance(ann.get("points"), list)
    # volume_breakout has an invalidation level -> an auto-derived stop level.
    assert any(l.get("kind") == "stop" for l in ann["levels"])
```

- [ ] **Step 2: Run, verify fail** — no `annotations` key.

- [ ] **Step 3: Implement**
- `base.py` `SignalMatch`: add a field
  ```python
      annotations: dict = field(default_factory=lambda: {"levels": [], "points": []})
  ```
  (after `factors`). It's optional for detectors — default empty.
- `signal_scan_service.py`: when building the `snapshot` dict, include annotations + auto-derive the stop from invalidation:
  ```python
  ann = {"levels": list(m.annotations.get("levels", [])),
         "points": list(m.annotations.get("points", []))}
  inv = m.invalidation or {}
  inv_level = inv.get("level") if isinstance(inv, dict) else None
  if isinstance(inv_level, (int, float)) and not any(l.get("kind") == "stop" for l in ann["levels"]):
      ann["levels"].append({"label": "Stop / invalidazione", "price": float(inv_level), "kind": "stop"})
  snapshot = {
      "tone": m.tone, "confidence": m.confidence, "chain": m.chain,
      "factors": m.factors, "invalidation": m.invalidation,
      "sources": getattr(_detector_for(m.name), "sources", []),
      "annotations": ann,
  }
  ```
- `frontend/src/api/types.ts`: extend `SignalSnapshot`:
  ```ts
  export interface SignalLevel { label: string; price: number; kind: string; }
  export interface SignalPoint { date: string; price: number; }
  // in SignalSnapshot:
  annotations?: { levels: SignalLevel[]; points: SignalPoint[] };
  ```

- [ ] **Step 4: Run + commit** — targeted + full suite green; `cd frontend && npm run build` (typecheck the new type).
```bash
git add backend/app/signals/detectors/base.py backend/app/signals/signal_scan_service.py backend/tests/signals/test_annotations.py frontend/src/api/types.ts
git commit -m "feat(signals): SignalMatch.annotations + auto-stop level in snapshot"
```

---

### Task P1-T2: chart_pattern shape points + neckline level

**Files:**
- Modify: `backend/app/signals/chart_patterns.py` (carry pivot dates in the event payload)
- Modify: `backend/app/signals/detectors/chart_pattern.py` (emit `annotations` with neckline level + shape points)
- Test: `backend/tests/signals/test_chart_pattern_detector.py`

- [ ] **Step 1: Add failing test** — the ChartPattern detector emits `annotations` with a `neckline` level + a non-empty `points` list (the shape). Inject a `chart_pattern` event carrying the new `points` payload:
```python
def test_chart_pattern_annotations_have_neckline_and_points():
    df = _df(103)  # existing helper; breaks above neckline 100
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0,
                             "points": [{"date": "2026-01-20", "price": 90.0},
                                        {"date": "2026-01-28", "price": 100.0},
                                        {"date": "2026-02-05", "price": 90.5}]})]
    m = ChartPattern().detect(events, df, build_context(df))
    assert m is not None
    levels = m.annotations["levels"]; points = m.annotations["points"]
    assert any(l["kind"] == "neckline" for l in levels)
    assert len(points) >= 2
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement**
- `chart_patterns.py` `extract_chart_patterns`: for each emitted `chart_pattern` event, add a `points` list to its payload — the (date, price) of the pattern's vertices. The function already has the pivot INDICES + the `dates`/`low`/`high` series; for each pattern build points:
  - double_bottom: `[(date[a], low[a]), (date[neck_i], high[neck_i]), (date[b], low[b])]`.
  - double_top: `[(date[a], high[a]), (date[neck_i], low[neck_i]), (date[b], high[b])]`.
  - inverse_head_shoulders: `[(date[s1], low[s1]), (date[head], low[head]), (date[s2], low[s2])]`.
  - head_shoulders: the 3 highs.
  - ascending/descending/symmetrical triangle: the last 3 highs + 3 lows as points (or just the converging pivots).
  Add `"points": [{"date": _iso(dates.iloc[i]), "price": float(series.iloc[i])}, ...]` to each event's payload.
- `chart_pattern.py` detector: build `annotations`:
  ```python
  neckline = p.payload.get("neckline")
  pts = p.payload.get("points") or []
  annotations = {
      "levels": [{"label": "Neckline", "price": float(neckline), "kind": "neckline"}]
                if isinstance(neckline, (int, float)) else [],
      "points": [{"date": str(pt["date"])[:10], "price": float(pt["price"])}
                 for pt in pts if isinstance(pt.get("price"), (int, float))],
  }
  ```
  and pass `annotations=annotations` to the returned `SignalMatch`. (The auto-stop in P1-T1 adds the stop separately from invalidation.)

- [ ] **Step 4: Run + commit** — targeted + full suite green.
```bash
git add backend/app/signals/chart_patterns.py backend/app/signals/detectors/chart_pattern.py backend/tests/signals/test_chart_pattern_detector.py
git commit -m "feat(signals): chart_pattern annotations (neckline level + shape points)"
```

---

### Task P1-T3: divergence points + primary levels for the level-bearing detectors

**Files:**
- Modify: `backend/app/signals/detectors/rsi_divergence.py`, `macd_divergence.py`, `hidden_divergence.py` (shape points from the price pivots)
- Modify: `backend/app/signals/detectors/volume_breakout.py`, `high52_momentum.py`, `sr_flip.py`, `oversold_reversal.py`, `candle_reversal.py`, `structure_break.py` (primary level beyond the auto-stop)
- Test: per-detector tests (extend existing)

- [ ] **Step 1: Divergence points.** For `rsi_divergence`/`macd_divergence`/`hidden_divergence`: the event payload has `pivot_dates` (two dates). In `detect`, look up the close price at those dates from `ohlcv` (match on the `date` column) and emit `annotations.points = [{date, price}, {date, price}]` (the divergence line on price). levels stay []. Add a test asserting `points` has 2 entries.
- [ ] **Step 2: Primary levels.** Each of these emits one extra level (the auto-stop already covers invalidation):
  - `volume_breakout`: `{"label":"Breakout","price":<bo level>,"kind":"breakout"}` (the breakout level from `payload`/the detector).
  - `high52_momentum`: `{"label":"Max 52w","price":hi_52,"kind":"resistance"}` (the 52w high).
  - `sr_flip`: `{"label":<role>,"price":level,"kind":"support"|"resistance"}` (the flipped level).
  - `oversold_reversal`: `{"label":<loc>,"price":nearest,"kind":"support"|"resistance"}`.
  - `candle_reversal`: `{"label":<loc>,"price":nearest,"kind":"support"|"resistance"}`.
  - `structure_break`: `{"label":"Livello protetto","price":protected,"kind":"support"|"resistance"}`.
  Set `annotations={"levels":[...], "points":[]}` on each returned SignalMatch. Extend each detector's test to assert its specific level is present.
- [ ] **Step 3: Run + full suite + commit.** The minimal detectors (squeeze_expansion, gap_and_go, adx_confirmation, pead, analyst_momentum, trend_pullback, insider_buy) need NO change here — they get the auto-stop (where invalidation exists) + frontend markers; their `annotations` stay default-empty otherwise.
```bash
git add backend/app/signals/detectors/ backend/tests/signals/
git commit -m "feat(signals): divergence shape points + primary levels for level-bearing detectors"
```

---

## Self-review notes
- Auto-stop derived once in `signal_scan_service` from `invalidation` → no per-detector repetition; the ~11 detectors with invalidation get a stop line free. ✓
- chart_pattern carries the shape (`points`) — the flagship "sagoma" (W / H&S / triangle); divergences carry their 2-pivot price line. ✓
- Level-bearing detectors add their one primary level (breakout / 52w / S-R / protected) beyond the stop. ✓
- Minimal/momentum detectors need no P1 work (auto-stop + markers suffice). ✓
- Contract uniform (`{levels:[{label,price,kind}], points:[{date,price}]}`); TS type added. Markers from chain dates (frontend, P2). ✓

## Follow-up — Phase P2
OHLCV endpoint `GET /api/stocks/{ticker}/ohlcv?bars=120` + `SignalChartSvg` (close line/area + level lines + shape polyline + numbered chain markers) + `useSignalOhlcv` + `AlertDetailDialog` integration + dist rebuild.
