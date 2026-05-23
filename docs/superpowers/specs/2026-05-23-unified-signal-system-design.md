# Unified Signal System — Master Design

**Status:** design approved in brainstorming (user mandate to proceed autonomously on remaining choices).
**Date:** 2026-05-23
**Supersedes:** `2026-05-23-signal-engine-design.md` (Phase 1 technical engine) — that engine becomes the foundation this design generalises.
**Scope:** the full program (architecture + catalog + migration + phasing). Each phase gets its own spec → plan → implementation cycle; this is the master.

---

## 1. Goal

Collapse the two parallel alerting mechanisms (the **atomic rule engine** and the **signal engine**) into **one** system: a single, curated, professionally-grounded catalog of **signals**. Every surfaced alert is a signal — a *chain of ≥2 events* (a primary pattern/setup plus at least one confirmation) carrying tone, a 0–100 confidence, a dated event timeline, an invalidation level, and a cited source.

The old rule engine, its API, its UI, and all historical rule-based alerts are **removed entirely** (total cleanup). Bare indicator conditions (RSI < 30, a single MA cross, a lone candle) are **never** alerts on their own — they become **events** that confirm or compose signals.

Non-technical information (earnings, analyst actions, insider activity) enters the **same** event stream and can reinforce or compose signals, exactly like technical events.

---

## 2. Core principles

1. **Atomic-never-alone.** Layer A (atomic events) — technical *and* non-technical — is never surfaced. Only Layer B/C/D detectors (and hybrid detectors) appear in the feed. Enforced structurally: atomic extractors are not in the detector registry; every detector's `detect()` requires a primary structure **plus ≥1 confirmation event**.
2. **Confirmation drives confidence.** Each detector defines 2–4 sub-factors in [0,1] (pattern quality, confirmation strength, trend alignment, location at S/R, volume, etc.). `confidence = round(100 · weighted_mean(factors))`. More/stronger confirmations → higher confidence. The single global gate `SIGNAL_MIN_CONFIDENCE` (default 60) decides what becomes an alert; detectors emit whenever structurally present.
3. **Curated, not configurable.** No user thresholds, no composite builder. Parameters are sensible curated defaults, adaptive to the timeframe (as indicator periods already are). This is a deliberate trade of flexibility for a clean, professional, auditable catalog.
4. **Layered & additive.** New detectors and new event producers (including the non-technical ones) plug into the existing 3-layer framework without reshaping it. This is the central payoff already proven in Phase 1a/1b.
5. **Deterministic & transparent.** No ML. Every signal is explainable (the chain), testable (synthetic fixtures), and citable (sources).

---

## 3. Architecture

```
Per ticker, during scan_universe (OHLCV already loaded):

  OHLCV ──► technical extractors ─┐
                                  ├─►  gather_events(db, stock, ohlcv) ─► list[Event]
  db/cache ─► fundamental         ┘     (technical + non-technical, date-sorted)
             producers
             (earnings/analyst/insider, read from existing two-tier cache)
                                  │
                                  ▼
              build_context(ohlcv) ─► SignalContext (trend, ATR, volatility regime, S/R levels)
                                  │
                                  ▼
              DETECTORS (B setups + C geometric + D candlesticks + hybrid)
                  each: primary + ≥1 confirmation → SignalMatch | None
                                  │
                                  ▼
              SIGNAL_MIN_CONFIDENCE gate + recency guard + dedup
                                  │
                                  ▼
              Alert(signal_name, snapshot={tone,confidence,chain,factors,
                    invalidation,sources}) ─► feed + Telegram + dashboard
```

**Multi-source event layer (chosen approach: fetch-on-demand in scan).** Technical events come from the OHLCV DataFrame already loaded. Non-technical events come from the existing services (`stock_fundamentals_service` for earnings/analyst/insider) which are already L1+L2 cached — read on-demand inside the scan loop, microseconds on a cache hit, 24h TTL. **No new tables, no new jobs** (B/C alternatives rejected for YAGNI). `Event` gains a `source` field (`technical|earnings|analyst|insider`) for UI grouping.

**Package layout (target):**
- `app/signals/events/technical.py` — OHLCV extractors (current + expanded atomic set).
- `app/signals/events/fundamental.py` — earnings/analyst/insider event producers (read db + cached services).
- `app/signals/events/__init__.py` — `Event`, `gather_events(db, stock, ohlcv)`.
- `app/signals/context.py` — `SignalContext` (extended: + S/R pivot levels, volatility regime).
- `app/signals/detectors/` — one module per detector + `base.py` + `registry.py`.
- `app/signals/pivots.py` — shared swing/zigzag pivot engine (needed by geometric + S/R + divergence).
- `app/signals/runner.py` — `detect_signals(db, stock, ohlcv)`.
- `app/signals/signal_scan_service.py` — SignalMatch → Alert (dedup + recency + threshold).

---

## 4. The catalog

### Layer A — Atomic events (confirmations/components, never surfaced)

**Technical (from OHLCV):** EMA/SMA cross (golden/death), price-vs-EMA200, ADX trend (+DI/−DI), EMA slope; RSI extreme, RSI divergence (regular + hidden), MACD cross (signal + zero-line), MACD divergence, Stochastic extreme; Bollinger touch/breach, BB squeeze (vs Keltner), ATR expansion, NR7; volume spike, OBV trend, volume dry-up, volume climax; Donchian breakout (N-day high/low), 52w high/low, gap up/down, support/resistance pivot level, trendline break, mean-reversion z-score; raw candlestick shapes (feed Layer D).

**Non-technical (from cached services):** `earnings_surprise` (beat/miss + surprise %, post-earnings gap), `analyst_change` (upgrade/downgrade, target raise/cut, recommendation shift), `insider_cluster` (buy cluster = strong, sell cluster = weak).

### Layer B — Multi-step technical setups (signals)

B1 Volume-Confirmed Breakout ✅ · B2 Trend-Pullback ✅ · B3 RSI Regular Divergence ✅ · B4 Squeeze→Expansion ✅ · B5 52-Week-High Momentum ✅ · B6 MACD Divergence · B7 Hidden Divergence (continuation) · B8 Cross + MA Retest · B9 Support/Resistance Flip · B10 Mean-Reversion Bounce · B11 Gap-and-Go vs Gap-Fill · B12 Oversold/Overbought at Level · B13 ADX Trend Confirmation · B14 Market-Structure Break (BOS/CHoCH).

### Layer C — Geometric / chart patterns (signals; confirmed by neckline/trendline break + volume)

C1 Double Bottom/Top (W/M) · C2 Triple Bottom/Top · C3 Head-and-Shoulders (top + inverse) · C4 Triangles (ascending/descending/symmetrical) · C5 Flag/Pennant (continuation) · C6 Rectangle (range) breakout · C7 Wedge (rising/falling) · C8 Cup-and-Handle · C9 Rounding Bottom.
*Excluded as low-ROI/noisy:* Wolfe wave, scallop, roof, broadening, diamond, island, bump-and-run (addable later if missed). Ranked per Bulkowski reliability.

### Layer D — Candlestick patterns (signals; ALWAYS confirmed by trend + location + volume)

Single: Hammer/Hanging Man, Inverted Hammer/Shooting Star, Doji (dragonfly/gravestone), Marubozu.
Double: Engulfing (bull/bear), Piercing/Dark Cloud Cover, Harami (+ cross), Tweezer top/bottom.
Triple: Morning/Evening Star (+ doji), Three White Soldiers/Three Black Crows, Three Inside Up/Down, Three Outside Up/Down.

### Layer B-ext — Hybrid signals (technical + non-technical concatenated)

H1 **PEAD / Earnings-Gap Breakout** (beat/miss + gap + volume + hold) — *Bernard & Thomas (1989), post-earnings drift.*
H2 **Analyst-Upgrade Momentum** (upgrade/target-raise + breakout).
H3 **Insider-Buy Confirmation** (insider buy cluster + oversold reversal at support).
H4 **Earnings + Divergence Reversal** (surprise + RSI/MACD divergence).

*(Non-technical sources in scope: earnings, analysts, insider. Macro + news/sentiment are explicitly deferred.)*

---

## 5. Confidence & confirmation model

Each detector returns `SignalMatch(name, tone, confidence, signal_date, chain[{date,label,detail,source}], invalidation, factors)`. Factors are clamped [0,1]; gate-confirmation factors (always-true-when-emitted) are kept in `factors` for display but excluded from the score weights (lesson from Phase 1b). The recency guard (`signal_max_age_days`) and `(stock, signal_name, signal_date)` dedup carry over unchanged.

---

## 6. Migration — total cleanup (irreversible, user-approved)

- **Delete** historical rule alerts: `DELETE FROM alerts WHERE rule_id IS NOT NULL` (before dropping the column).
- **Drop** `Alert.rule_id` column + its index/FK; `rule_kind` becomes purely `signal:<signal_name>`.
- **Drop** tables `rules`, `rule_states` (alembic, batch mode for SQLite).
- **Remove** backend: `app/rules/` package (atomic rules, composite tree, RuleState), `app/api/rules.py`, rule references in `scan_service` (the rule-evaluation sub-phase), `alert_service`, `stats_service`, `notifier_service`, `api/alerts.py`, `stock_detail_service`.
- **Adapt** `rule_performance_service` → **signal performance** (forward-return efficacy keyed by `signal_name`); SettingsPage "Efficacia regole" → "Efficacia segnali".
- **Remove** frontend: `RulesPanel`, `RulesTable`, `RuleEditorDialog`, `useRules`, `api/rules`, the composite-expression builder + `RuleExpressionNode` types, the rule-kind metadata entries in `alertMeta` (replaced by the signal catalog metadata).
- The `/alerts` page keeps the signal feed; loses rule management. A read-only **"Catalogo segnali"** view (what detectors are active + their sources) replaces the rules panel.

A safety note will be added to CLAUDE.md: the "catalog has duplicate ticker rows" and "two-tier cache" notes still apply; a new note documents that signals are the only alert source.

---

## 7. Phasing (each phase = own spec → plan → implementation)

- **Phase U1 — Foundations + cleanup.** Multi-source event layer scaffolding (`gather_events`, `source` field), expand technical atomic events, the shared pivot engine, port B1–B5 to the confirmation model, and execute the **total rule cleanup** (migration + code/UI removal + signal-performance adaptation). Ships a working signals-only system.
- **Phase U2 — Technical breadth.** B6–B14 + Layer D candlesticks (all confirmed).
- **Phase U3 — Non-technical + hybrids.** `fundamental.py` event producers (earnings/analyst/insider) + H1–H4 hybrid detectors.
- **Phase U4 — Geometric.** Pivot/zigzag-based C1–C5 (most reliable) then C6–C9.

Ordering rationale: U1 unifies + de-risks (cleanup is the riskiest, do it first while context is fresh); U2/U3 are additive on the proven scaffold; U4 (geometric) is the hardest/noisiest, last.

---

## 8. Error handling & testing

- Every extractor/producer guards insufficient data → `[]`; non-technical producers also guard cache-miss / upstream error → `[]` (never block the scan).
- Each detector + the whole signals sub-phase run in `try/except` (logged, skipped) — a failure never aborts the scan.
- Tests: synthetic OHLCV fixtures per extractor/detector (deterministic); event-injection for detectors whose setup is hard to synthesize; golden tests pin confidence factors; integration tests assert scan emits well-formed signal alerts and that a producer failure is non-fatal. Keep the suite green.

---

## 9. Key decisions (rationale)

1. **One system, rules deleted** (vs keep both): the user's explicit goal; removes drift and double-maintenance.
2. **Curated catalog, no user config** (vs configurable): cleaner, professional, auditable; the composite builder + custom thresholds were power-user features the user chose to drop.
3. **Atomic-never-alone** (vs surface atomics): matches professional practice — confirmation lifts candlestick/indicator reliability from ~50–60% to materially higher; also solves the noise problem (e.g. Phase 1b's prolific trend_pullback) by construction.
4. **Fetch-on-demand multi-source events** (vs precompute table / event store): reuses the existing two-tier cache, additive, no new infra (YAGNI).
5. **Total cleanup incl. history** (vs soft retire): user-approved; maximal cleanliness; accepted irreversibility.
6. **Phased, each its own spec/plan** (vs one mega-spec): the program is far too large for a single plan; phasing keeps each increment working and reviewable.

---

## 10. Out of scope

- Macro + news/sentiment events (deferred; the framework leaves the seam open).
- Any ML / learned scoring.
- User-facing thresholds, per-rule config, custom composite builder.
- A separate "Signals" dashboard (output stays as enriched alerts).

---

## 11. Sources (grounding for the catalog)

- Bulkowski, *Encyclopedia of Chart Patterns* (3rd ed.) — chart-pattern catalog + reliability ranking (thepatternsite.com).
- Nison, *Japanese Candlestick Charting Techniques* — candlestick patterns + the principle that context/confirmation drives reliability.
- Murphy, *Technical Analysis of the Financial Markets* (CMT core text) — classic setups (breakout/pullback/divergence/S-R flips).
- Wilder (1978) RSI; Bollinger (2001) + TTM Squeeze; George & Hwang (2004) 52-week-high momentum; Brock, Lakonishok & LeBaron (1992) MA rules; Bernard & Thomas (1989) post-earnings drift.
