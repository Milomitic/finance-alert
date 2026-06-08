# Signal Reinforcement & Confluence — Design

**Date:** 2026-06-09
**Status:** Draft for review
**Scope decision (user):** Implement *everything, phased* (1 → 2 → 3 → 4) with a review checkpoint between phases. Phases 3–4 touch backtest-validated scoring/targets and are gated behind their own checkpoint + re-validation.

---

## 1. Problem statement

The user opened a META signal popup: a **bearish "Trend + Pullback" (Continuazione)**, signal_date 2026-05-26, trigger 612.34, invalidation 651.32 ("chiusura oltre EMA200 contro il trend"). Their observation: beyond "ritorno a EMA / pullback", the engine does **not** also detect and chain the obvious reinforcing events — e.g. *the price returning up to EMA200 and being rejected back down* — nor does it let multiple events in the same time window stack into stronger conviction and **different targets**.

Three structural facts (all code-verified) explain this:

1. **The "EMA test / reject" event does not exist.** The only EMA-level event is the *cross*: `extract_ema_cross` (`backend/app/signals/events.py:82`) emits only on EMA50/EMA200 sign-change. The pullback test lives inline in `trend_pullback.py:47-54` (price within a flat `_PULLBACK_TOL = 0.015` of EMA50 over the last 20 bars) and produces **no reusable `Event`**. A return-to-EMA200-and-reject has no primitive.

2. **`TrendPullback` is "event-blind".** It filters `events` to `e.type == 'ema_cross'` only (`trend_pullback.py:35`). The same `events` list already carries `candle_reversal`, `rsi_extreme`, `rsi_divergence`, `volume_spike`, `sr_level`, and `macd_cross` — none are read. **`macd_cross` is extracted every scan (`events.py:255`, registered at `events.py:402`) but consumed by no detector at all.**

3. **Confluence is read-only and never reaches the score or the playbook.**
   - `confluence_service.compute_confluence` (`backend/app/services/confluence_service.py:87`) clusters active alerts within a flat `signal_max_age_days = 7` window and computes a cluster strength via `_dir_strength` (`confluence_service.py:74`): `base + (CEIL−base)·(1−DECAY^(n−1))`, `_CONFLUENCE_CEIL = 98`, `_CONFLUENCE_DECAY = 0.5`. This is **ephemeral** — it never writes back to `Alert.snapshot.strength`/`.probability`.
   - `buildPlaybook(s, entry, name)` (`frontend/src/lib/tradePlaybook.ts:86`, called at `AlertDetailDialog.tsx:339` as `buildPlaybook(alert.snapshot ?? {}, alert.trigger_price, alert.rule_kind ?? null)`) derives R/targets purely from `invalidation.level`, `atr`, and `horizon` (HZ table, `tradePlaybook.ts:41-48`). Confirmation count is never an input.
   - `signal_calibration.json` has `factor_adjustments: {}`, so Probabilità is each detector's flat base-rate.

**Net:** even when several bear detectors co-fire on META, the `trend_pullback` alert stays at its solo Forza, flat Probabilità, and confirmation-blind targets. The user's intuition is not just unimplemented — it is structurally impossible in the current data flow.

---

## 2. Goals & non-goals

**Goals**
- Surface co-temporal confirming events (incl. the EMA200 test-and-reject) as **chained Catena steps** the user sees.
- Widen the event/detector pool with the missing primitives.
- Let genuinely-independent confirmation move **Forza** and **Probabilità** — *correctly*, without double-counting correlated detectors.
- Let conviction move **targets and sizing** — *targets only widen, the structural stop never loosens*.
- Make co-temporal windows and the horizon label faithful to the actual timeframe.

**Non-goals (invariants that must NOT break)**
- The `score_v2` anti-laundering contract: a strong context factor must never rescue a weak core. New "confirmation" factors enter **outside `strength_keys`** (they lift the arithmetic mean via the `_V2_DELTA = 0.12` channel, capped by the weakest genuine strength factor).
- The structural stop = `invalidation.level`. Confirmation never widens or loosens the stop.
- The Forza 99 ceiling and the Probabilità `[5, 95]` clamp with `_PROB_MAX_ADJ = 8.0` per-factor cap.
- The backtest-validated HZ target geometry (`tradePlaybook.ts:34` "VALIDATED by backtest 2026-05-25"): any target change is gated + re-validated, never shipped blind.
- No new alert spam: enrichment grows **one** primary alert's chain; it does not mint duplicate alerts.

---

## 3. Architecture overview

Current flow:
```
extractors(events.py) → events[]  ──►  detectors.detect(events, ctx) → SignalMatch
                                          │  (each detector reads only its own event type)
                                          ▼
                              signal_scan_service: dedup → Alert(snapshot=match)
                                          ▼
   confluence_service.compute_confluence (read-time cluster, dead-ends)
                                          ▼
   frontend: buildPlaybook(snapshot)  ── confirmation-blind
```

Target flow (new components in **bold**):
```
extractors (+ ema_interaction, swing_pivot)  → events[]
        │
        ▼
   detectors.detect → SignalMatch (primary)
        │
        ▼
   **enrich_chain(match, events)** — append co-temporal same-tone confirmations to chain;
                                     set factors["confirmation_count"], factors["confluence_n_eff"]
        ▼
   signal_scan_service: dedup → Alert(snapshot=enriched match)
        ▼
   **confluence_service (de-correlated effective count)** → effective_forza + bounded prob bump
        ▼
   frontend: buildPlaybook(snapshot, entry, name, **confluence?**) — targets/size scale with conviction
```

The key design move: a single **chain-enrichment pass** between `detect` and persist (Phase 1), fed by **new event primitives** (Phase 2), whose output (a `confirmation_count` and a de-correlated effective-N) becomes the substrate that **scoring** (Phase 3) and **targets** (Phase 4) consume.

---

## 4. Phase 1 — Chain enrichment (display + evidence)

**Intent:** the Catena grows with the confirmations already present in the event stream. Zero new extraction. No score/target change yet (the `confirmation_count` factor is *plumbed* but its scoring weight is 0 until Phase 3, so Forza is unchanged here — it only appears in the chain UI).

**New module:** `backend/app/signals/chain_enrichment.py`
```
def enrich_chain(match: SignalMatch, events: list[Event], ctx: SignalContext,
                 *, window_bars: int = 5, max_appends: int = 5) -> SignalMatch
```
- Operates only on matches whose `name` is a continuation/trend setup (start with `trend_pullback`; extend to the `_TREND_FOLLOWING_SIGNALS` set behind the same helper).
- Scans `events` for **same-tone** events whose date is within `window_bars` trading bars of `match.signal_date` AND not already represented in `match.chain`. Confirmation taxonomy (bear example; bull mirrors):
  - `candle_reversal` (shooting-star / bearish-engulfing) near the EMA → "Rifiuto candela su EMA".
  - `rsi_extreme` or `rsi_divergence` (bear) → "RSI in rollover".
  - `volume_spike` on a down-bar → "Volume sulla discesa".
  - `sr_level` retest-as-resistance → "Retest supporto rotto".
  - `macd_cross` (bear) → "MACD cross ribassista". *(This is the dead-event recovery.)*
  - `ema_reject` / `swing_pivot` (Phase 2 events) when present.
- Appends each as a numbered chain step `{date, label, detail}` (existing shape; the frontend `SignalSnapshotView` renders numbered tech steps automatically).
- Sets `match.factors["confirmation_count"] = min(n_appended, 3) / 3` (0..1, bounded). **Not** added to any detector's `strength_keys` and weight stays 0 in Phase 1.

**Wiring:** call `enrich_chain` in `runner.py` (or at the top of `signal_scan_service` before dedup) so every persisted snapshot is enriched. Enriched steps carry the **same `signal_date` bar** as the primary (or strictly within the window) so `classify_horizon` (which uses chain span) is not skewed — see §8.

**Horizon-safety:** because `classify_horizon` (`horizon.py:41`) reads the chain's min/max date span, appended steps must be **bounded to the co-temporal window** and the span computation must ignore enrichment steps (use only the detector's own cause+resume dates). Implementation: tag enrichment steps with `{"kind": "confirmation"}` and have `classify_horizon` span over non-confirmation steps only.

**Tests:** unit tests on `enrich_chain` with synthetic events (right tone in-window → appended; wrong tone / out-of-window / duplicate → skipped; `confirmation_count` bounded; horizon span unchanged by enrichment). Frontend: chain renders N steps.

**Checkpoint 1:** user sees the META chain grow (Death cross → Pullback+ripresa → … → MACD cross). Forza/Probabilità/targets unchanged. Approve before Phase 2 land or proceed together (both low-risk).

---

## 5. Phase 2 — New event primitives (widen pool)

**Intent:** turn the user's literal ask ("ritorno verso EMA200 + rifiuto") and the lower-high tell into first-class, dated, chainable events.

**2a. EMA-interaction extractor** — `extract_ema_interaction(df, fast=50, slow=200)` in `events.py`, added to `EXTRACTORS`:
- For each bar, against EMA50 and EMA200:
  - `ema_test`: the bar's high/low came within `k·ATR` of the EMA but closed back on the trend side.
  - `ema_reject`: intrabar pierce of the EMA then close rejected away with a directional body (bear = pierced up toward EMA from below, closed below).
  - `ema_return`: close re-entered the EMA cluster band.
- Emit `Event(date, "ema_reject"/"ema_test"/"ema_return", direction, magnitude=|close−EMA|/ATR, payload={"ma": "ema200"|"ema50", "side": ...})`.
- **ATR-scaled proximity** (`k·ctx.atr`), not a fixed %, to respect volatility regime.

**2b. Continuation-pivot extractor** — emit a `swing_pivot` event (using `find_pivots` from `pivots.py`, already used by `structure_break`) tagged `payload={"continuation": True}` when the newest confirmed high is **below** the prior swing high in a downtrend (lower-high) or newest low **above** prior low in an uptrend (higher-low). This is the pullback-exhaustion tell *before* a full structure break. Note the intrinsic `width`-bar confirmation lag in the chain detail.

**2c. ATR-scaled pullback tolerance in `TrendPullback`** — replace flat `_PULLBACK_TOL = 0.015` with `tol = max(0.015, k · ctx.atr / close)` (floor at current value so it only ever *loosens* for high-vol names). `ctx.atr` is already available (`context.py:18`).

**2d. (Optional, same phase) `MaRejection` detector** — once `ema_reject` exists, a dedicated detector firing when price returns to an EMA (esp. EMA200) and is rejected with momentum confirmation. **Own calibration bucket** (see §6) so it doesn't re-count the same EMA evidence as `trend_pullback` in confluence. Needs its own `base_rate` via `signal_detector_outcomes --emit-map`; until then degrades to neutral 50.

**Validation gate:** before wiring new events into any score, measure their **emission frequency** on a sample of tickers (must not flood the stream) and spot-check on META + a few others.

**Tests:** extractor unit tests (synthetic OHLCV producing a known reject/test/return; lower-high/higher-low pivots; ATR-tol loosens only upward). `MaRejection` detector unit tests if included.

**Checkpoint 2:** the chain on META now explicitly shows "Rifiuto su EMA200 (ritorno giù)" and "Lower-high confermato". Still no score/target change. Approve before Phase 3.

---

## 6. Phase 3 — Confluence → conviction (scoring) ⚠ backtest-sensitive

**Intent:** let *independent* agreement move Forza and Probabilità — without the cross-detector mediocrity-laundering that naive count-stacking would cause.

**6a. De-correlation buckets.** Assign every detector to a correlation family; confluence counts **distinct families** (or sqrt-discounts within a family), not raw detectors:
- **ema-trend**: `trend_pullback, volume_breakout, adx_confirmation, high52_momentum, structure_break, squeeze_expansion, gap_and_go, sr_flip` (mirrors the existing `_TREND_FOLLOWING_SIGNALS` set in `signal_scan_service.py:25` — reuse it as the seed).
- **pivot-momentum**: `rsi_divergence, macd_divergence, hidden_divergence`.
- **level/reversal**: `oversold_reversal, candle_reversal` (+ `ma_rejection` if added).
- **pattern**: `chart_pattern`.
- **fundamental**: `pead, analyst_momentum, insider_buy`.

Effective independent count `n_eff` = number of distinct families that fired in the cluster (with optional `+0.3` per extra same-family member, capped). Implement in `confluence_service._dir_strength` (replace raw `n` with `n_eff`), keeping `_CONFLUENCE_CEIL = 98` and `_CONFLUENCE_DECAY = 0.5`.

**6b. Forza flow.** Keep per-alert `snapshot.strength` **immutable** (preserves calibratability and the audit trail). Expose a derived `effective_forza = min(99, round(strength + confluence_lift(n_eff)))` on the confluence cluster and surface it in the UI; `confluence_lift` is bounded (≤ ~12pp) and 0 when `n_eff ≤ 1`. The per-detector `score_v2` cap is never bypassed.

**6c. Probabilità flow (calibrated, not invented).** Populate `factor_adjustments` in `signal_calibration.json` with a `confirmation_count` (and/or `confluence_n_eff`) entry, **generated by the existing harness** `app.scripts.signal_detector_outcomes` / `signal_factor_outcomes`: bucket each detector's realised forward hit-rate by number of co-temporal confirmations (0/1/2/3+) over the 10y `ohlcv_daily`, no look-ahead. Wire `confirmation_count` into the `factors` dict so `probability_from_factors` (`base.py:270`) picks up the adjustment, still under the `_PROB_MAX_ADJ = 8.0` cap and `[5, 95]` clamp. If the study shows confirmations don't improve forward hit-rate, the adjustment stays ~0 — a valid, falsifying result.

**Operational note:** the calibration run reads OHLCV and writes `signal_calibration.json`; per CLAUDE.md, stop uvicorn first (sole SQLite writer) and run with `PYTHONPATH=.`.

**Tests:** `_dir_strength` de-correlation (3 correlated ema-trend bears → `n_eff ≈ 1`, not 3; one per family → `n_eff = k`); `confluence_lift` bounds; probability adjustment honors caps; calibration loader picks up the new factor.

**Checkpoint 3 (mandatory):** review the calibration output and the before/after Forza/Probabilità distribution on a sample (incl. META) before exposing the boosted numbers. Approve before Phase 4.

---

## 7. Phase 4 — Targets respond to conviction ⚠ backtest-sensitive

**Intent:** deliver "extra confirmations should impact the targets" — conservatively.

- Extend `buildPlaybook(s, entry, name, confluence?)` with an optional 4th arg `confluence?: { nEff: number; multiHorizon: boolean; effectiveForza: number }`, joined from the data already enriched into the snapshot (Phase 1/3) or the `/api/alerts/confluence` endpoint the frontend already fetches.
- Effect, **only when `nEff ≥ 2` (and ideally `multiHorizon`)**:
  - (a) widen **TP2 only** by a bounded factor (e.g. `tp2R`/`tp2Cap` ×(1 + up to ~0.2)) — aligned-confirmation continuations historically ran further;
  - (b) raise the conviction label and the position-size budget beyond solo Forza.
- **Never** touch the stop. **Never** widen TP1 past its validated cap such that hit-rate degrades.

**Re-validation gate:** the HZ geometry was validated under a "TP-hit ≥ 25%" constraint. Any TP2 widening must be replayed against the same backtest harness; if TP2 hit-rate drops below threshold, shrink or drop the widening. Ship behind a flag.

**Tests:** `buildPlaybook` with/without confluence (stop identical; TP2 widens only when gated; TP1 unchanged; sizing scales). Snapshot/regression on a few known alerts.

**Checkpoint 4:** review target deltas on a sample + backtest expectancy before enabling by default.

---

## 8. Time contextualization

- **Recency-weighted co-temporal kernel.** Replace the flat 7-day confluence window + ad-hoc per-detector `within_days` with a shared kernel that weights a corroborating event by proximity to the primary `signal_date` (full weight same bar, decaying over ~5–10 bars) and *requires* chain-appended events to fall inside it. Prevents stale (e.g. 4-month-old) levels from chaining as if fresh.
- **Horizon-from-cause fix.** `classify_horizon` (`horizon.py:41`) currently derives the label from the chain's date span, so an old death cross with a short recent chain is mis-labeled. Fix: span over the **cause** steps (cross + resume), ignore enrichment steps; keep the detector's horizon prior when the cause is old. This matters because the horizon label selects the entire target geometry (HZ table).
- **(Stretch / future phase) Multi-timeframe agreement.** The same pullback is "continuation" on the daily but "exhaustion" on the intraday. Evaluate the setup across ranges (the engine already has range-adaptive indicator periods) and reward cross-timeframe agreement. Flagged **L effort, out of the initial 4-phase scope** — list as an open follow-up, not committed here.

---

## 9. Data model / migration impact

- **No DB schema change required** for Phases 1–2: chain steps and `factors` live inside `Alert.snapshot` (JSON). `confirmation_count` is a `factors` key.
- Phase 3: no schema change — `signal_calibration.json` data file is regenerated; `effective_forza` is derived/served, not stored.
- Phase 4: no schema change — confluence context is passed to the frontend, not persisted.
- **Backfill:** existing alerts won't have enriched chains. Acceptable (legacy alerts already show "n/d · legacy" for missing slots). Optional one-off re-enrichment script for active alerts if desired at Phase 1 close.

---

## 10. Risks & mitigations (summary)

| Risk | Mitigation |
|---|---|
| Cross-detector mediocrity laundering (correlated detectors inflate conviction) | De-correlation buckets; `confirmation_count` outside `strength_keys`; bounded `confluence_lift`; calibrate, don't invent |
| Chain bloat with stale events | Tight ATR-aware co-temporal kernel; `max_appends` cap; same-bar/in-window only |
| Horizon mis-classification shifting target geometry | Span over cause steps only; keep detector prior when cause is old; ship horizon fix separately |
| Target widening degrading validated expectancy | Re-run backtest; TP2-only, gated on `nEff ≥ 2`/multiHorizon; flag; stop never touched |
| New events flooding the stream | Frequency check on a ticker sample before wiring into score |
| Probabilità bump unjustified | Driven only by the no-look-ahead calibration harness; ~0 if no real edge |

---

## 11. Phase sequencing & checkpoints

1. **Phase 1** (chain enrichment, display-only) → Checkpoint 1.
2. **Phase 2** (new primitives + ATR tol; optional `MaRejection`) → Checkpoint 2.
3. **Phase 3** (de-correlated confluence → Forza/Probabilità, calibrated) → Checkpoint 3 (mandatory data review).
4. **Phase 4** (targets/size respond, re-validated) → Checkpoint 4.

Each phase is independently shippable and reversible; Phases 3–4 require the explicit data/backtest review at their checkpoint before enabling by default.

---

## 12. Open questions for the user

1. **Phase-1 scope of detectors:** start enrichment on `trend_pullback` only, or all `_TREND_FOLLOWING_SIGNALS` from the outset? (Recommend: `trend_pullback` first, then widen.)
2. **`MaRejection` detector:** include the dedicated detector in Phase 2, or keep the EMA reject as a *chain confirmation only* until Phase 3 proves it adds independent edge? (Recommend: chain-only first; promote to detector if calibration shows edge.)
3. **Multi-timeframe (§8 stretch):** in scope now as a 5th phase, or explicitly deferred? (Recommend: deferred follow-up.)
