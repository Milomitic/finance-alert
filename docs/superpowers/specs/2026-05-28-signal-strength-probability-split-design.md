# Signal "Confidence" → "Forza" + "Probabilità" split — Design

**Date:** 2026-05-28
**Status:** approved (model + sub-phases), implementing B1

## Goal

Eliminate the single `confidence` score on each signal and replace it with **two
independent first-class attributes**:

- **Forza** (strength, 0–100): how strong / clean the pattern-trend is.
- **Probabilità** (probability, 0–100): the empirical likelihood the signal
  works (historical forward hit-rate of comparable signals).

All other signal attributes (horizon, tone, chain, invalidation, factors,
trade playbook) are **unchanged**.

## Motivation — what the 10-year outcome study proved

Two read-only harnesses were built over 10y / 1440 stocks / 3.4M OHLCV bars
(`app/scripts/signal_factor_outcomes.py`, `signal_detector_outcomes.py`):

1. **Marginal factor magnitude is mostly NOT predictive, market-neutral.**
   - `oversold_reversal.rsi_extremity`: +2÷3% edge, ~52.8% hit (works).
   - `squeeze.tightness`, `volume_strength`: predict move *size*, not direction.
   - `gap_size`, `breakout_strength`, `adx_strength`: **mean-revert** — bigger
     magnitude → *worse* forward return (gap −2.2%, adx −4.8% at the extreme).
2. **The detector CONJUNCTION carries edge the marginals don't.** e.g.
   `adx_confirmation` detector is net **+1.15%** though the ADX factor alone is
   strongly mean-reverting; `volume_breakout` detector +0.79% though the
   breakout factor alone is negative. Gates + trend context rescue the signal.
3. **Current `confidence` is ~flat vs outcome** (hit-rate by band:
   <60→51%, 60–70→49%, 70–80→49%, 80–90→52%, 90+→54%). It is essentially a
   pattern-strength score wearing a probability costume.

**Conclusion:** a single number cannot honestly express both "this is a textbook-
strong pattern" and "this historically works". A monster gap is *high Forza, low
Probabilità*. Splitting tells the whole truth and resolves the mean-reversion
tension natively (no need to flatten strength curves — Probabilità carries it).

## The model

Per signal, computed at detection time:

### Forza (strength)
- Per factor: a calibration curve on the raw magnitude that rewards genuine
  pattern strength — `concave(x, anchors)` for bounded factors,
  `log_saturate(x, ceil)` for unbounded ratios (volume). Anchors placed by the
  factor's empirical distribution (rarity) — Forza legitimately rises with
  magnitude even for mean-reverting factors (a big gap IS a strong pattern).
- Combine: `score_v2(factors, weights, strength_keys)` — weighted mean capped
  by a soft-min over the STRENGTH factors (kills "mediocrity laundering":
  a saturated context factor can't drag a mediocre strength factor into the top
  band). Context modulators (alignment, maturity) lift `arith` but are excluded
  from the soft-min so their weakness isn't double-counted.
- All three (`concave`, `log_saturate`, `score_v2`) shipped in Phase A.

### Probabilità (probability "di accadimento")
The user's concept is the probability the **signalled move actually occurs** —
an ABSOLUTE directional hit-rate, NOT a market-relative edge. (Market-neutral
excess is the right lens for "does this factor add stock-selection skill", and
is how we UNDERSTOOD which factors matter — finding #1/#2 — but it is the wrong
lens for "will the move happen": a bull signal in a rising tape genuinely is
more likely to go up, and the user wants that truth.)

So Probabilità is grounded in **detector-level ABSOLUTE forward hit-rate** at the
detector's horizon (P(close moved the signalled way after h days)), modulated by
per-factor adjustments where a factor measurably shifts that probability.

```
probability = clamp( base_rate_abs[detector, horizon]
                     + Σ adj_k(factor_k_raw) )     in [p_floor, p_ceil]
```

- `base_rate_abs[detector, horizon]`: the detector's historical ABSOLUTE
  directional hit-rate (0–100), from `signal_detector_outcomes`. Naturally
  spread (oversold ≠ high52 ≠ divergence; bear signals lower over a bull decade)
  — so the scale is informative, unlike the flat market-neutral edges. Stored in
  the generated calibration map.
- `adj_k`: small bounded additive adjustment (±~8 pts) for factors whose value
  within the detector shifts the hit-rate (from `signal_factor_outcomes`). Most
  ≈0; oversold-depth and tightness/volume (move-size) are the meaningful ones.
- Factors with no/low-sample data contribute 0 adjustment (neutral).
- HONESTY NOTE shown in UI copy/tooltip: Probabilità is the historical
  occurrence rate of comparable signals over the chosen horizon — it is regime-
  dependent (measured over 2016–2026, a mostly-rising decade), not a guarantee.

Both the absolute base rate (for Probabilità) AND the market-neutral edge (for
our internal validation / future skill-weighting) are emitted by the harness.
This is a **base-rate + adjustment** model — defensible v1. Multivariate
(logistic) calibration and regime conditioning are future work.

## Architecture

```
signal_detector_outcomes.py  ──(--emit-map)──►  app/data/signal_calibration.json
signal_factor_outcomes.py    ──(--emit-map)──►        (committed artifact)
                                                          │ loaded at startup
                                                          ▼
app/signals/calibration_map.py  (loader + lookup: base_rate, factor adj)
                                                          │
app/signals/detectors/base.py:                           │
  score_v2(...)            → Forza                        │
  probability_from_factors(detector, factors, horizon) ◄──┘ → Probabilità
                                                          │
each of 17 detectors: SignalMatch(strength=…, probability=…, factors=…)
                                                          │
signal_scan_service: snapshot{strength, probability, …}; emission gate
                                                          │
alert API / schemas: expose strength + probability       │
                                                          ▼
frontend: two badges "Forza" / "Probabilità" everywhere confidence appeared
```

- **Calibration map** = committed JSON (deterministic, versioned, no runtime DB
  dependency). Regenerated by re-running the harnesses with `--emit-map`. This
  mirrors the existing `app/data/calibration_seed.json` pattern.

## Data model & API changes

- `SignalMatch`: replace `confidence: int` with `strength: int` + `probability:
  int`.
- snapshot JSON: add `strength`, `probability`. Keep `confidence` written =
  `strength` during a transition window for back-compat readers, then drop.
- `Alert` table: `confidence` is NOT a column (it lives in snapshot) → no
  migration needed for the column; backfill is a snapshot rewrite.
- Emission gate (`signal_scan_service` line ~85): `signal_min_confidence` →
  replace with `signal_min_strength` (keep the same 60 default initially; the
  distribution shifts so revisit). Probabilità does NOT gate emission (a low-
  probability strong pattern is still worth surfacing — that's the point).
- API (`app/api/alerts.py`, `app/services/alert_service.py`, confluence
  schemas): expose both; sort/filter by either.
- `confluence_service`: today aggregates `confidence`; switch its strength input
  to Forza, and surface aggregate Probabilità alongside.
- Existing calibration (`calibration_seed.json` + consumers): reconcile — the
  "confidence→hit-rate" panel becomes redundant with Probabilità being the
  hit-rate directly; fold/retire in B2.

## Frontend surfaces (inventory for B3)

Every "Confidenza" reference → two values. Known surfaces: alerts table
(column + sort + filter), `AlertDetailDialog` / signal snapshot view, confluence
card + rows, top-confluence, dashboard signal panels, alertMeta tone maps, trade
playbook header, screener signal facet. Full grep sweep at B3 start.

## Migration of legacy alerts (2233 rows)

Backfill `strength` + `probability` into existing snapshots by re-deriving from
the stored `factors` where present (strength via `score_v2`; probability via the
calibration map using the stored detector name + factors). Rows without usable
factors → `strength = confidence` (best effort), `probability = base_rate` only.
Mark un-derivable legacy rows so the UI shows "n/d" rather than a wrong number.

## Sub-phases (each: TDD, full suite green, commit)

- **B1 — backend two-score model.** Calibration map generator (`--emit-map`) +
  committed JSON + `calibration_map.py` loader; `probability_from_factors` in
  base.py; `SignalMatch` two-score; migrate all 17 detectors; snapshot +
  emission gate; scan integration test. Restart uvicorn + verify /api/health.
- **B2 — scan/API/confluence/calibration + migration.** Expose both in
  schemas/API; confluence + calibration reconciliation; legacy backfill script;
  regenerate current alerts.
- **B3 — frontend.** Replace all confidence UI with Forza + Probabilità badges,
  sort/filter, detail; rebuild `frontend/dist`; hard-reload note.

## Testing strategy

- Curves + combiner: covered (Phase A, 23 tests).
- `calibration_map` loader: unit tests (lookup, missing-key neutral fallback,
  bounds).
- `probability_from_factors`: unit tests (base-rate dominates, adjustments
  bounded, clamp).
- Each migrated detector: update its test to assert the two scores for a
  representative case (strength behaves like old confidence sans knee;
  probability ≈ base rate ± adjustment).
- Distribution-shift integration test: re-derive a fixture of representative
  signals, assert Forza distribution (fewer ≥85 than old confidence) and
  Probabilità distribution (centred near the empirical base rates, monotone-ish
  vs realised hit where measurable).

## Open questions / future work

- Probability granularity: v1 detector-base-rate + factor adjustments. Future:
  multivariate (logistic) calibration; regime conditioning (bull/bear); per-
  horizon base rates beyond the single natural horizon.
- Whether to retire `confidence` from the snapshot entirely after the transition
  window, or keep as a derived alias.
- Emission threshold semantics once the Forza distribution settles.
