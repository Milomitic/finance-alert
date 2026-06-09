# Engine Quality v1 — Design

**Date:** 2026-06-09
**Status:** Approved to implement (user: proceed without further approvals; implement the whole block, propose value-adds along the way).

First slice of the engine-improvement roadmap (`docs/superpowers/specs/` workflow synthesis). Grounded in this session's empirical findings: single-name technicals are ~coin-flips, `confirmation_count` has no edge, `multi_horizon` is a weak directional marker. The theme of v1 is **honesty + substrate**: stop crediting market beta as skill, surface the coin-flip/negative-edge reality, frame scores cross-sectionally, and build the persistent outcome store that makes every later improvement cheap and validatable.

## Scope (4 items)

### A — Beta-stripped "skill" for signals (#2, quick-win, signals)
Probabilità today consumes only `base_rate` (absolute close-to-close hit), which flatters bull/high-beta detectors. The artifact ALREADY stores `mkt_neutral_hit` + `mkt_neutral_edge_pct` per detector. Expose a **skill** view (market-neutral) so display + future ranking key off skill, not absHit. No change to the emission gate (stays on Forza) and no change to the stored Probabilità number yet — this is surfacing + plumbing.

- `CalibrationMap`: add `skill(d)` = `mkt_neutral_hit`, `edge_pct(d)` = `mkt_neutral_edge_pct`, `sample_n(d)` = `n`.

### B — Honesty markers on signals (#6, quick-win, signals)
A detector-level quality tag derived from the artifact, surfaced in the alert detail next to Probabilità, plus the existing drift line:
- `quality_tag(d)`: `"negative"` if `edge_pct < -0.3` (e.g. structure_break −1.46%); `"coinflip"` if `base_rate ∈ [48,52]` AND `|edge_pct| < 0.3`; else `"edge"`. (Given the empirics, most technical detectors → coinflip.)
- These are **detector-level facts** → served by a lookup endpoint, NOT stored per-alert (always current; zero backfill; covers all existing alerts).
- The drift line reuses `signal_drift_service.compute_signal_drift` (already Wilson-CI, n≥30 gated) via the existing `/api/platform/signal-drift`.

**Backend:** `GET /api/signals/calibration` → `{ detectors: { name: {base_rate, skill, edge_pct, n, horizon_days, tag} }, version }` from `get_calibration()`.
**Frontend:** `AlertDetailDialog` fetches the table (cached query keyed by nothing — process-wide), looks up the alert's detector, renders: the skill value beside Probabilità, and a chip — amber "≈50/50 storico" (coinflip) / red "edge storico negativo" (negative). No scoring change.

### C — Sector / universe percentile on the Qualità score (#15, quick-win, score-qualità)
A composite of 72 is meaningless absolutely; "9th pct in Tech vs 80th in Utilities" is decision-useful and matches the engine's own sector-relative thinking.
- **Backend:** windowed SQL rank over `StockScore.composite` joined to `Stock.sector` → `sector_percentile`, `universe_percentile`, `peer_n` added to `StockScoreOut`. Use the existing `ix_stock_scores_composite`. "campione esiguo" when `peer_n < 8`.
- **Frontend:** `StockScoreCard` renders "Top X% del settore (n=…)".

### D — Persistent `signal_outcomes` warehouse + maturation (#1, the substrate)
Append-only table capturing, **causally at signal time**, the labeled forward outcome of every signal alert. Collapses the three duplicated forward-hit implementations into one and turns every later validation (walk-forward CV, regime conditioning, ranking, recalibration, score IC) from a multi-minute replay into a SQL query.

- **Model/migration:** `signal_outcomes` (alembic; mirror the append-only `KpiSnapshot` precedent; `op.batch_alter_table` for SQLite). Columns: `id`, `alert_id`, `stock_id`, `detector`, `signal_date`, `tone`, `horizon_days`, `entry_close`, `forward_close`, `fwd_return`, `universe_mean_fwd`, `mkt_neutral_excess`, `abs_hit`, `mkt_neutral_hit`, `regime_at_signal` (causal `close>EMA200`), `breadth_at_signal` (nullable until regime_states exists), `rvol_at_signal`, `sector_pct_at_signal`, `earnings_in_window`, `strength`, `probability`, `factors_json`, `matured_at`.
- **Maturation service** (`signal_outcome_service`): one shared forward-hit function (the SINGLE source of truth, replacing `signal_drift_service._forward_hit` / `signal_detector_outcomes._trade_playbook_hit` / `rule_performance_service._forward_close` over time). Runs at the end of `run_tracked_scan` over alerts whose horizon has elapsed in stored `ohlcv_daily`; writes one row per (alert, horizon) once mature; never re-writes (None-guard on missing forward bar = no-look-ahead by construction).
- **Backfill** once from the historical replay.
- **Validation = PARITY, not edge:** assert per-detector `mean(abs_hit)` / `mean(mkt_neutral_excess)` from the table reproduce `signal_calibration.json` base_rate / mkt_neutral_hit within sampling noise, and store-derived recent-window hit equals `compute_signal_drift` on the same alert set.

## Invariants (do NOT break)
- No scoring change from confirmation/confluence/multi_horizon (proven null/weak).
- Emission gate stays on Forza; lenses stay decoupled (signals don't touch Qualità/Tecnico composites).
- Stops/targets stay structural/backtest-validated.
- No new model flips production Probabilità/composite without the purged walk-forward gate (a later roadmap item). v1 ships **surfacing + substrate only** — it makes no new edge claim.

## Sequencing
1. **A+B backend** (CalibrationMap methods + `/api/signals/calibration`) — TDD, no risk.
2. **A+B frontend** (skill + honesty chips + drift line in the dialog).
3. **C** (sector/universe percentile) backend + frontend.
4. **D** (warehouse): model + migration → maturation service → wire into scan → backfill → parity validation.

Each step is independently shippable, tested, committed. Later roadmap items (purged walk-forward CV, regime/breadth gate, score_history+IC, cross-sectional signal-rank, RVOL gate, earnings clip, reliability page) build on D and are pursued next, each validated before any production score/target change. Proactive value-adds welcome as they surface.
