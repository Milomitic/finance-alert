# Signal Engine — Design (Phase 1)

**Status:** approved direction; design finalized by the agent per user mandate.
**Date:** 2026-05-23
**Scope:** Phase 1 only (technical signals). Phases 2–3 sketched for context.

---

## 1. Goal & motivation

Today's alert engine fires on **point-in-time predicates**: each rule's
`evaluate(ohlcv) -> bool` is checked on the *last bar*. A composite tree
(`app/rules/composite.py`) already allows boolean `AND/OR` of atomic rules,
but it is still evaluated on a single bar — it has no notion of *time*,
*structure*, or *confidence*.

The user wants **true signals**: chains of concatenated events (technical
and, later, non-technical) that replicate recognised bullish/bearish
setups and trend confirmations, grounded in scientific papers / consolidated
trading models — surfaced through the **existing alert flow (Telegram +
feed) but enriched** with confidence, tone, and the event chain that
produced them.

Three dimensions are missing from today's engine and must be added:

1. **Time / sequence** — "event A, *then* B within N bars" (e.g. golden
   cross → pullback to the moving average → resume; breakout → volume
   confirmation within 3 sessions).
2. **Structure / price-action patterns** — divergences now; geometric
   figures (double top/bottom, head-and-shoulders, flags) in Phase 2.
3. **Confidence / score** — a 0–100 bullish/bearish confidence instead of
   a bare boolean trigger.

The chosen direction (confirmed with the user) is a **mix of all three**,
over **all event sources** (technical + per-stock fundamentals + macro/news),
surfaced as **enriched alerts**. Because that is too large for one spec, it
is decomposed into phases; **this spec covers Phase 1**.

---

## 2. Phased decomposition

- **Phase 1 — Technical signal engine** (this spec): the 3-layer framework +
  the first 5 grounded signals, on OHLCV only, integrated into enriched
  alerts with a richer alert UI.
- **Phase 2 — Geometric price-action patterns**: double top/bottom,
  head-and-shoulders, flags/triangles — added as new detectors on the same
  framework. Purely additive.
- **Phase 3 — Non-technical events**: earnings beat/miss + surprise, analyst
  upgrades/downgrades, insider, then macro (CPI/FOMC from the calendar) and
  news sentiment — added as new **event producers** feeding the same event
  stream; existing detectors can then concatenate them. Purely additive.

Phases 2 and 3 do not rewrite anything: they add detectors and event
sources. This is the central payoff of the layered design (§4).

---

## 3. Architecture overview

New package `app/signals/` (sibling to `app/rules/`, which is untouched).
Three layers, evaluated during the daily scan immediately after the existing
rule evaluation, on the **same OHLCV DataFrame already loaded** by
`scan_universe` (no extra fetches):

```
OHLCV (per ticker, ~260 bars already loaded by scan_universe)
   │
   ▼
[1] Event extractors  ──►  list[Event]      (DATED facts over the recent
   │                                          window — not just the last bar)
   ▼
[2] Signal detectors  ──►  SignalMatch|None (consume events with time
   │                         windows/sequences → tone + confidence + chain)
   ▼
[3] Signal → Alert    ──►  Alert(rule_kind="signal:<name>",
                                 signal_date, snapshot=chain)  → feed + Telegram
```

---

## 4. Layer 1 — Event extractors

An **event** is a dated, JSON-serialisable fact:

```python
@dataclass(frozen=True)
class Event:
    date: str               # ISO YYYY-MM-DD — the bar the fact occurs on
    type: str               # "ema_cross" | "breakout" | "volume_spike"
                            #  | "rsi_divergence" | "bb_squeeze" | "bb_expansion"
                            #  | "macd_cross" | "rsi_extreme" | ...
    direction: str | None   # "bull" | "bear" | None
    magnitude: float | None # normalised strength (vol ratio, % amplitude, ...)
    payload: dict           # details for the UI/snapshot (levels, periods, pivots)
```

Each extractor is `extract(ohlcv: pd.DataFrame) -> list[Event]` and scans the
**recent window** (default last ~120 bars; the scan already loads 260, so
the window is free), emitting **dated** events across that window — *not just
the last bar*. This is the key difference from the atomic rules, which only
answer "true on the last bar".

Phase-1 extractors (technical only):

| Extractor | Emits | Notes |
|---|---|---|
| `ema_cross` | `ema_cross` (bull=golden, bear=death) | fast/slow EMA crossover dates |
| `breakout` | `breakout` (bull/bear) | close beyond N-day Donchian / 52w extreme |
| `volume_spike` | `volume_spike` | vol/vol_avg_20 ≥ k; magnitude = ratio |
| `rsi_divergence` | `rsi_divergence` (bull/bear) | regular divergence over pivots |
| `bollinger` | `bb_squeeze`, `bb_expansion` | BB width inside/expanding vs Keltner |
| `macd` | `macd_cross` (bull/bear) | signal-line crossover dates |
| `rsi_extreme` | `rsi_extreme` (bull=oversold, bear=overbought) | RSI < 30 / > 70 |

Extractors reuse the existing indicator math (`app/indicators/`); they are
new code because the atomic `Rule.evaluate` returns a single bool, whereas
extractors must emit dated events over a window.

**Why a separate event layer (vs detectors reading OHLCV directly):**
composability and Phase 3. A divergence is reused by several signals; computing
it once as an event avoids N duplications. And in Phase 3, "earnings beat" or
"FOMC dovish" become *new event producers* — the detectors that concatenate
them don't change shape.

---

## 5. Layer 2 — Signal detectors

```python
@dataclass(frozen=True)
class SignalMatch:
    name: str                      # detector name, e.g. "rsi_divergence"
    tone: str                      # "bull" | "bear"
    confidence: int                # 0..100
    signal_date: str               # ISO — date of the chain's last event
    chain: list[dict]              # [{date, label, detail}] — the "why"
    invalidation: dict | None      # {"level": float, "reason": str}
    factors: dict[str, float]      # sub-scores [0..1] for transparency/UI

class SignalDetector(Protocol):
    name: str
    tone: str                      # default tone (a detector may emit both)
    sources: list[str]             # citations (papers / consolidated models)
    min_bars: int
    def detect(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: "SignalContext",
    ) -> SignalMatch | None: ...
```

- **Sequences / windows.** Detectors locate events in order with temporal
  constraints via small helpers, e.g. `find_after(events, type, direction,
  after=date, within=N)`. This is where "A then B within N bars" lives.
- **Confidence — deterministic & transparent (no ML in Phase 1).** Each
  detector defines 2–4 sub-factors normalised to [0,1] (e.g. divergence
  amplitude, alignment with the EMA200 trend, volume strength vs its average,
  ATR/volatility regime). `confidence = round(100 · weighted_mean(factors))`.
  The detector emits a `SignalMatch` **whenever the pattern is structurally
  present** (it does NOT apply a confidence cutoff itself); the single
  alerting threshold in §7 (`SIGNAL_MIN_CONFIDENCE`) decides what becomes an
  alert. The factors are carried in `SignalMatch.factors` and rendered in
  the UI.
  - *Rationale:* explainability + testability + no labelled dataset. ML is
    premature (no ground-truth labels, high overfit risk on ~1k tickers); a
    transparent scoring keeps signals auditable and unit-testable, and is
    itself the precursor data should we later train a model.
- **`SignalContext`** is computed once per ticker and passed to every
  detector: EMA200 slope (trend sign/strength), ATR (to normalise amplitudes),
  volatility regime. Avoids recomputing shared features per detector.
- **Isolation.** A registry lists active detectors; the runner calls each in
  a `try/except` — a detector that raises is logged and skipped, never
  blocking the others or the scan.

---

## 6. Phase-1 signal catalog (grounded)

Five detectors, all deterministic (no geometry — that's Phase 2), covering
reversal / continuation / breakout / momentum, bull and bear via direction.
Each cites a paper or consolidated model (stored in `sources`, surfaced in
the UI tooltip):

1. **RSI Regular Divergence** (`rsi_divergence`, bull/bear)
   Price makes a lower low while RSI makes a higher low (bull), or mirror for
   bear. *Source: Wilder, "New Concepts in Technical Trading Systems" (1978).*
2. **Trend-Pullback Continuation** (`trend_pullback`, bull/bear)
   Golden cross (50/200 EMA) → pullback toward the moving average → resume in
   the trend direction. *Source: Brock, Lakonishok & LeBaron, "Simple Technical
   Trading Rules…" (Journal of Finance, 1992) on MA crossover rules; pullback
   entry as the consolidated refinement.*
3. **Volume-Confirmed Breakout** (`volume_breakout`, bull/bear)
   Close beyond an N-day Donchian high (bull) / low (bear) accompanied by a
   volume spike. *Source: Donchian channel breakout + volume confirmation
   (Granville on-balance-volume lineage).*
4. **Volatility Squeeze Expansion** (`squeeze_expansion`, bull/bear)
   Bollinger Bands contract inside Keltner Channels (squeeze) → expansion that
   resolves in the trend direction. *Source: Bollinger, "Bollinger on Bollinger
   Bands" (2001); TTM Squeeze, Carter, "Mastering the Trade".*
5. **52-Week-High Momentum** (`high52_momentum`, bull)
   Price at/near its 52-week high with a positive trend. *Source: George &
   Hwang, "The 52-Week High and Momentum Investing" (Journal of Finance, 2004).*

---

## 7. Layer 3 — Scan integration, dedup, output

- **Where:** a `signals` sub-phase inside `scan_universe` (or a
  `signal_scan_service` called from it), running on the OHLCV DataFrame
  already loaded for each stock → **zero extra fetches**.
- **Emission:** each `SignalMatch` becomes
  `Alert(rule_kind="signal:<name>", signal_date=<chain last event>,
  triggered_at=now, snapshot=json({tone, confidence, chain, factors,
  invalidation}))`.
- **Dedup / edge-trigger:** before inserting, skip if an `Alert` already
  exists with the same `(stock_id, rule_kind, signal_date)`. A new trigger
  has a new `signal_date`, so this reproduces the existing edge-trigger
  behaviour without virtual `Rule`/`RuleState` rows.
  - *Rationale:* minimal surface, reuses the `Alert` table + its
    feed/notifier pipeline; signals are naturally edge-triggered by their
    `signal_date`.
- **Alerting threshold:** only emit an alert when `confidence ≥
  SIGNAL_MIN_CONFIDENCE` (settings/constant, default 60). No config UI in
  Phase 1 (YAGNI).
- **UI (enriched alert):** when `rule_kind` starts with `signal:`, the alert
  feed + detail render the **event chain** as a dated timeline, plus a
  confidence badge, the bull/bear tone, the cited source, and the
  invalidation level. The snapshot JSON already carries everything.

---

## 8. Error handling

- Extractors are defensive: insufficient OHLCV (`< min_bars`) → `[]`.
- Each detector runs in `try/except`; a failure is logged
  (`logger.warning`) and skipped — never blocks the scan or other detectors.
- The whole signals sub-phase is wrapped so a failure there cannot abort the
  alert scan (the existing rule alerts must still fire).

---

## 9. Testing

- **Extractors:** synthetic OHLCV crafted to contain / not contain each fact
  (deterministic fixtures); assert the event is emitted on the right date with
  the right direction/magnitude.
- **Detectors:** fixtures that contain the full setup → assert a `SignalMatch`
  with expected tone and a confidence in an expected band; flat/contrary
  series → assert `None`. Golden tests pin the confidence factors.
- **Dedup:** same setup over consecutive scans emits the alert once.
- **Integration:** `scan_universe` on a fixture stock produces an
  `Alert` with `rule_kind="signal:*"` and a well-formed snapshot; and a
  signals failure does not prevent the legacy rule alerts.

Backend target: keep the suite green (currently 594 tests) + new tests per
extractor/detector.

---

## 10. Key design decisions (with rationale)

1. **Separate event layer** (vs detectors reading OHLCV): composability
   (events reused across signals) and a free Phase-3 seam (non-technical
   events are just new producers).
2. **Named hardcoded detectors** (vs a sequential DSL): fidelity to the
   papers, room for Phase-2 geometry as ordinary code, and per-detector
   testability + citability. A boolean/sequential DSL cannot express
   geometric figures without becoming a programming language.
3. **Deterministic transparent confidence** (vs ML): explainable,
   testable, no labelled data; ML is premature and overfit-prone now.
4. **Reuse `Alert` + `(stock,kind,signal_date)` dedup** (vs a new `signals`
   table / virtual rules): minimal surface; reuses feed + Telegram + the
   edge-trigger semantics.
5. **~120-bar event window** off the already-loaded 260 bars: captures
   multi-week sequences at no fetch cost.
6. **Global confidence threshold for alerting** (no per-signal config UI in
   Phase 1): keeps noise low without UI scope creep.

---

## 11. Out of scope (Phase 1)

- Geometric price-action patterns (Phase 2).
- Non-technical event sources — earnings/analyst/insider/macro/news (Phase 3).
- Any ML / learned scoring.
- A user-facing builder/DSL to compose custom signals.
- A dedicated "Signals" dashboard (output is enriched alerts, per user choice).

---

## 12. New / touched files

**New (`app/signals/`):** `events.py` (Event + extractors), `context.py`
(SignalContext), `detectors/` (one module per signal + `base.py` Protocol +
`registry.py`), `runner.py` (extract → detect → SignalMatch list),
`signal_scan_service.py` (SignalMatch → Alert + dedup).
**Touched:** `scan_service.py` (call the signals sub-phase), `settings`
(`SIGNAL_MIN_CONFIDENCE`), alert schema/serialisation if the snapshot needs a
typed shape, frontend alert feed/detail components (render the chain +
confidence + tone for `signal:*` kinds).
