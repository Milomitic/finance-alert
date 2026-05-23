# Unified Signals — Phase U3: non-technical events + hybrid signals

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Bring earnings / analyst / insider events into the same signal stream (multi-source event layer) and add hybrid detectors that concatenate technical + non-technical events — the flagship being PEAD (Post-Earnings-Announcement Drift).

**Architecture:** The runner gains a multi-source `gather_events(db, stock, ohlcv)` = technical extractors (OHLCV, as today) + **cache-only** non-technical producers. Hybrid detectors consume the merged stream like any other detector. Full suite stays green (598 passed / 1 skipped at U3 start).

**Tech Stack:** Python 3.11, pandas, SQLAlchemy, pytest. Reads `stock_fundamentals_service` (`Fundamentals` with `earnings: list[EarningsPoint(date, eps_estimate, eps_reported, surprise_pct)]`, `insiders: list[InsiderTransaction]`, `analyst_actions: list[AnalystAction]`).

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; ASCII-only; gate factors excluded from `score` weights.

> ⚠️ **CRITICAL DESIGN CONSTRAINT — cache-only producers.** The non-technical producers run inside the per-stock scan loop over ~900 stocks. They MUST read ONLY already-cached fundamentals (L1 `_CACHE` and/or L2 `fetch_cache` table) and MUST NOT trigger an upstream yfinance fetch. A cache miss → return `[]` (graceful: that stock simply gets no non-technical events this scan). Implement a cache-only accessor in `stock_fundamentals_service` (e.g. `get_fundamentals_cached(ticker) -> Fundamentals | None` that returns the cached value or None, never fetching) and use it from the producers. This is the single most important correctness/perf requirement of U3.

---

### Task 1: Multi-source event layer (gather_events) — the load-bearing refactor

**Files:**
- Modify: `backend/app/signals/runner.py` (signature + gather), `backend/app/signals/signal_scan_service.py` (call site)
- Create: `backend/app/signals/events_fundamental.py` (producers — stubs returning [] in this task; real logic in T2-T4)
- Test: `backend/tests/signals/test_runner.py` (adapt), `backend/tests/signals/test_gather_events.py` (new)

- [ ] **Step 1:** Add `gather_events(db, stock, ohlcv) -> list[Event]` in `events_fundamental.py` (or a new `app/signals/events/__init__.py` — keep it ONE module to avoid churn): runs `extract_events(ohlcv)` (technical) + the three producers (`produce_earnings_events`, `produce_analyst_events`, `produce_insider_events`), each wrapped in try/except (a producer failure must NEVER break the scan), merges + date-sorts. In THIS task the three producers are stubs returning `[]`.
- [ ] **Step 2:** Change `runner.detect_signals(ohlcv)` → `detect_signals(db, stock, ohlcv)`: it calls `gather_events(db, stock, ohlcv)` instead of `extract_events(ohlcv)` directly. Keep the per-detector try/except. Keep `build_context(ohlcv)` (technical context).
- [ ] **Step 3:** Update `signal_scan_service.evaluate_signals` line ~36: `for m in detect_signals(db, stock, ohlcv):`.
- [ ] **Step 4:** Adapt `test_runner.py` (the `detect_signals` calls now need `db, stock` — pass a seeded stock + the in-memory `db`, OR keep a thin `detect_signals_from_events` helper for the pure-OHLCV unit tests). Add `test_gather_events.py` asserting gather merges technical + (stubbed-empty) non-technical without error. Full suite green.
- [ ] **Step 5: Commit** `refactor(signals): multi-source gather_events(db, stock, ohlcv)`.

**Safety:** this is load-bearing (touches the scan path). Verify `tests/test_scan_emits_signal_alerts.py` + the signals suite stay green. Run an in-process scan smoke on one real stock.

---

### Task 2: Earnings producer + PEAD hybrid (H1)

**Files:**
- Modify: `backend/app/services/stock_fundamentals_service.py` (add cache-only `get_fundamentals_cached`)
- Modify: `backend/app/signals/events_fundamental.py` (`produce_earnings_events`)
- Create: `backend/app/signals/detectors/pead.py`
- Modify: `registry.py`
- Test: `test_events_fundamental.py`, `test_pead.py`

- [ ] **Producer:** `produce_earnings_events(db, stock)` → read `get_fundamentals_cached(stock.ticker)`; for each recent `EarningsPoint` with a `surprise_pct` (reported), emit `Event(date=earnings_date, type="earnings_surprise", direction="bull" if surprise_pct>0 else "bear", magnitude=clamp(|surprise_pct|), payload={"surprise_pct":..., "eps_reported":..., "eps_estimate":...}, source="earnings")`.
- [ ] **PEAD detector (H1):** consume `earnings_surprise` + a same/next-bar `gap` (same direction) + a `volume_spike`. Bull: beat + gap up + volume → continuation. Confidence: surprise magnitude + gap size + volume. Source: Bernard & Thomas (1989). Chain shows beat -> gap -> volume.
- [ ] TDD each (event-injection for the detector); register `Pead()`; full suite green; commit.

---

### Task 3: Analyst producer + Analyst-Upgrade Momentum (H2)

- [ ] **Producer:** `produce_analyst_events(db, stock)` → from `Fundamentals.analyst_actions` (upgrade/downgrade/target changes), emit `Event(type="analyst_change", direction="bull"/"bear", magnitude=..., payload={action, firm, from_grade, to_grade}, source="analyst")` dated at the action date.
- [ ] **Detector (H2):** `analyst_change` (bull) + a confirming `breakout` or `ema_cross` bull within N days → momentum continuation. Confidence: action strength + technical confirmation. Register `AnalystMomentum()`; TDD; commit.

---

### Task 4: Insider producer + Insider-Buy Confirmation (H3)

- [ ] **Producer:** `produce_insider_events(db, stock)` → aggregate `Fundamentals.insiders` into clusters: if N+ distinct insiders BOUGHT within a window (or total bought shares above a floor), emit `Event(type="insider_cluster", direction="bull", magnitude=..., payload={n_buyers, total_shares}, source="insider")`. (Sells are weak — emit bear only on a strong cluster, lower weight.)
- [ ] **Detector (H3):** insider buy cluster + an `oversold`/`rsi_extreme` bull or at-support confirmation → high-conviction reversal. Register `InsiderBuy()`; TDD; commit.

---

### Task 5: Wire producers into gather_events + full integration + restart

- [ ] Replace the T1 stubs: `gather_events` now calls the three real producers (each try/except, cache-only). Confirm a scan over real cached stocks emits non-technical + hybrid signals where data exists, and stocks without cached fundamentals simply get no non-technical events (no fetch storm). Full suite green; in-process scan smoke; commit; restart backend; rebuild dist only if FE touched (it isn't in U3).

---

## Self-review notes
- Cache-only producers (no scan-time fetch) is enforced via `get_fundamentals_cached` — the key perf/correctness constraint. ✓
- `Event.source` (added in U1b) tags non-technical events for UI grouping. ✓
- Hybrids honor atomic-never-alone: PEAD = surprise+gap+volume; AnalystMomentum = action+technical; InsiderBuy = cluster+technical. ✓
- Load-bearing refactor (T1) isolated + green-gated before the additive producers/detectors. ✓
- Data shapes verified against `Fundamentals` (earnings/insiders/analyst_actions). ✓

## Follow-up
- **U4** — geometric chart patterns (double top/bottom, H&S, triangles, flags, wedges, cup&handle) on the existing `find_pivots` engine + neckline/trendline logic. Then enrich the alert UI to group the event chain by `source` (technical/earnings/analyst/insider).
- B7 hidden divergence (small): extend rsi/macd divergence extractors to emit hidden + a HiddenDivergence detector.
