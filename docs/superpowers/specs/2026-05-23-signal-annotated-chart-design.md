# Signal Annotated Chart (SVG in the detail popup) — Design

**Status:** design approved in brainstorming.
**Date:** 2026-05-23
**Scope:** add a static, self-rendered SVG mini-chart to the signal detail popup that visually explains the detected signal and the underlying event chain (price + annotated levels + pattern shape + numbered event markers).

---

## 1. Goal

When a user opens a signal alert in `AlertDetailDialog`, show — above the existing `SignalSnapshotView` — a compact **annotated chart** of the ticker that makes the signal legible at a glance: the recent price, the key **levels** (neckline / breakout / support / resistance / stop), the pattern **shape** (e.g. the W of a double bottom, the head-and-shoulders profile, a divergence trendline), and **numbered markers** on the bars where each chain event fired (matching the chain timeline 1, 2, 3…).

Confirmed design decisions:
- **Full annotation** (levels + shape), not just markers.
- **Static SVG** we render ourselves (no lightweight-charts) — a true "screen", no interactivity.
- **Detectors expose structured annotations** (Approach 1): the data comes from the detector that fired, not re-derived at serve time (no drift).
- **Price drawn as a close line/area** (cleanest at small size; annotations are the focus).

---

## 2. Data contract — `annotations` in the signal snapshot

Each detector adds an `annotations` object to its `SignalMatch` → persisted in the alert `snapshot`:

```python
annotations = {
    "levels": [          # horizontal lines
        {"label": str, "price": float, "kind": str},   # kind: neckline|breakout|support|resistance|stop
        ...
    ],
    "points": [          # ordered vertices of the pattern SHAPE (polyline); [] if no shape
        {"date": "YYYY-MM-DD", "price": float},
        ...
    ],
}
```

- **levels**: each detector emits the levels it ALREADY computes (e.g. `volume_breakout` → the breakout level; `chart_pattern` → the neckline; `sr_flip`/`oversold_reversal`/`candle_reversal` → the S/R level; `high52_momentum` → the 52w high; `structure_break` → the protected swing). The **stop** level is the existing `invalidation.level` re-expressed as `{kind:"stop"}` (so all 17 get at least a stop where invalidation exists).
- **points**: only the detectors with a genuine multi-point geometry fill this — `chart_pattern` (the W / triple / H&S / triangle vertices + neckline ends), `structure_break` (recent swings), `rsi_divergence` / `macd_divergence` (the two pivots forming the divergence). All others emit `points: []`.
- **markers**: NOT new data — the frontend places a numbered dot at each existing `chain[i].date`.

To draw the chart_pattern shape, the `chart_pattern` EVENT payload (in `events.py`) must also carry the pivot **dates** (today it carries neckline + pivot prices but not their dates). Small additive change to `extract_chart_patterns` + the detector forwards them as `points`.

**Typing:** Python — the snapshot is a free JSON dict; document the shape (no strict model needed). TS — extend `SignalSnapshot` (in `api/types.ts`) with `annotations?: { levels: SignalLevel[]; points: SignalPoint[] }`.

---

## 3. OHLCV access — a lightweight endpoint

The SVG needs the ticker's recent daily bars (just date + OHLC). Add:

```
GET /api/stocks/{ticker}/ohlcv?bars=120  ->  [{date, open, high, low, close}, ...]
```

Reads `OhlcvDaily` (the same source the scan uses), most-recent `bars`, ascending. Lighter than reusing `/detail` (which also returns indicators / news / kpis — over-fetch on every popup). Authed like the other stock endpoints. The window (≈120 daily bars) comfortably covers any daily signal's chain span; the frontend can also widen to include the earliest annotation/point date if older.

---

## 4. Frontend — `SignalChartSvg`

A self-contained SVG component (a scaled-up cousin of the existing `MiniSpark` in `EtfHoldingsCard`):

**Props:** `bars: {date,open,high,low,close}[]`, `annotations: {levels, points}`, `chain: SignalChainStep[]` (for marker dates), `tone: "bull"|"bear"`, optional width/height.

**Renders (layered):**
1. The **close price** as a line/area across the bars; tone colors it (emerald/rose).
2. **Level lines** — one horizontal line per `levels[]`, labeled (small text), the `stop` one **dashed** + amber.
3. **Shape polyline** — connect `points[]` (x mapped by date→bar index, y by price); a subtle accent stroke. Skipped when `points` is empty.
4. **Numbered markers** — a small numbered circle on the bar at each `chain[i].date`, index matching the timeline below.

Y-scale includes the level prices + points so nothing is clipped. X-scale by bar index; annotation dates map to the nearest bar. Defensive: missing bars/annotations → render what's available (or a "dati non disponibili" placeholder); never break the popup.

**Data fetch:** a hook `useSignalOhlcv(ticker, enabled)` (react-query) fetches the window only when the popup is open for a signal alert (lazy).

**Integration:** in `AlertDetailDialog`, for signal alerts only, render `<SignalChartSvg />` in a section between the hero strip and the `SignalSnapshotView` (the popup was widened to `max-w-2xl`, so there's room).

---

## 5. Phasing

- **P1 — Backend annotations.** Add the `annotations` block to all detectors (levels they compute + stop from invalidation; points for the ~5 geometric/structure/divergence ones, incl. the `chart_pattern` extractor carrying pivot dates). Add the TS `SignalSnapshot.annotations` type. Tests: each detector's snapshot carries well-formed `annotations.levels` (and `points` for the geometric ones). No UI yet.
- **P2 — OHLCV endpoint + SVG + integration.** The `/ohlcv` endpoint + `useSignalOhlcv` + `SignalChartSvg` + dialog integration; rebuild dist.

Each phase = its own implementation plan.

---

## 6. Error handling & testing

- Backend: detectors emit `annotations` defensively (a level only when its price is a finite number; `points` only when the geometry exists). A detector that can't build annotations emits empty lists — never raises.
- The `/ohlcv` endpoint: unknown ticker / no bars → empty list (200), not an error.
- Frontend: `SignalChartSvg` guards empty bars/annotations; the popup renders the rest (snapshot view) regardless.
- Tests: backend unit tests assert `annotations` shape per detector (levels present; points for chart_pattern); the endpoint returns the right window. Frontend verified via `npm run build` (typecheck) + manual; a vitest test can pin the SVG's level/point→coordinate mapping (pure math) if a setup exists.

---

## 7. Key decisions (rationale)

1. **Detectors author annotations** (vs re-derive at serve time): the chart shows exactly what the signal fired on — no window/param drift; clean data contract.
2. **Static SVG** (vs interactive chart): user choice; lighter, a true "screen", and the annotations (not pan/zoom) are the value.
3. **Close line/area** (vs candles): cleanest at small static size; annotations stay the focus.
4. **Dedicated `/ohlcv` endpoint** (vs reuse `/detail`): avoids over-fetching indicators/news on every popup open.
5. **Markers from the existing chain dates + levels from already-computed numbers**: ~80% of the annotation is near-free; new data (`points`) is confined to the few patterns that have a shape.

## 8. Out of scope

- Interactivity (zoom/hover) — it's a static screen.
- Candlestick rendering (line/area for v1).
- Multi-timeframe (daily only, like the engine).
- Shape outlines for non-geometric signals (they have no meaningful shape — levels + markers suffice).
