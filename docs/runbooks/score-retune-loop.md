# Runbook — Periodic, Validated, Human-in-the-Loop Score Retuning

**Status:** active · **Owner:** scoring · **Last reviewed:** 2026-05-29

This is the disciplined loop we run *periodically* (e.g. after a universe
refresh, a data-source change, or a quarter of new bars) to re-tune the scoring
stack. It is **NOT a continuous auto-tuner.** Every pass produces a **PROPOSAL**
that a human reviews and applies by hand. The anti-overfit discipline below is
the entire point — a single-name equity edge is a near-coin-flip, so the
dominant failure mode is *fitting noise and shipping a worse model that looks
better in-sample.*

> **The iron rule.** **REJECT the change unless it is CLEARLY better
> OUT-OF-SAMPLE.** Flat is a reject. Better in-sample but flat OOS is a reject.
> "I think it's more principled" is a reject without an OOS number. The default
> action is *keep the current params.*

---

## 0. The three lenses and their tunable families

The scoring stack is three orthogonal lenses (see `CLAUDE.md` → "Scoring
architecture"). Each owns a family of tunables, each with its OWN validation
harness and gate metric:

| # | Family (tunable) | Lens | Validation harness | Gate metric (OOS) |
|---|---|---|---|---|
| **A** | Fundamental **pillar weights** + per-component **ramp anchors** | Qualità | `app.scripts.entry_ic_report` (`--validate-*-retune`) | composite **rank-IC** at the slow horizon, disjoint test stocks |
| **B** | Signal **per-factor curve anchors** (`concave`/`log_saturate`) + **`score_v2` delta** | Segnali (Forza) | `signal_factor_outcomes` + `signal_detector_outcomes` | per-factor **monotonic hit-rate** + detector **base-rate spread** |
| **C** | **Probabilità base rates** / calibration model | Segnali (Probabilità) | `signal_detector_outcomes --emit-map` + `fit_signal_calibration` | **OOS Brier** (lower is better), disjoint-stock AND temporal split |

The orchestrator `app.scripts.retune` reports a **proposal diff + gate verdict**
for all three families in one read-only pass (see §5). It proposes; it never
applies.

---

## 1. The anti-overfit guardrails (read this before touching anything)

These are not optional and they are not per-family — they apply to **every**
retune, always:

1. **Split TRAIN/TEST on DISJOINT stocks.** The model must never see a ticker in
   both halves, or it memorises the ticker, not the signal. The gold-standard
   precedent is `frontend/src/lib/tradePlaybook.ts` (header: *"VALIDATED by
   backtest, train/test split on DISJOINT stocks"*). `fit_signal_calibration`
   additionally adds a **temporal** holdout (train old bars, test recent bars)
   and requires passing **both** splits.
2. **Regularize / prefer the simpler form.** Fewer free parameters beats more.
   Prefer **monotonic, interpretable** shapes (a PAVA isotonic map, an L2
   logistic, a 3-anchor ramp) over anything that can wiggle to fit a bucket. A
   curve that isn't monotonic in the underlying parameter needs an explicit,
   data-grounded reason (e.g. `trend_maturity_factor` is non-monotonic *by
   design* — forward returns genuinely peak mid-trend).
3. **No look-ahead, market-neutral where measuring skill.** Indicators at bar
   *i* use only bars ≤ *i*; the forward return is the only thing that looks
   past. Pivot-confirmed signals are only knowable `pivot_w` bars later. Use the
   **causal** regime feature (`close > EMA200` at the obs bar), never the
   universe forward mean (it leaks the label).
4. **Judge slow factors at slow horizons.** Fundamentals (value/quality/growth)
   express over **252d**, not 5–21d. Scoring them only at short horizons biases
   the whole exercise toward momentum.
5. **Gate on the metric, not the vibe.** A change ships only if
   `passes_oos_gate(baseline, candidate, ...)` returns `True` on the **held-out
   (test)** stocks. If you can't produce that number, you cannot ship the
   change.

### Precedents this discipline has already produced (cite these)

These are the reasons the guardrails exist — every one was a change that
*looked* reasonable and was **rejected (or removed) by the OOS evidence**:

- **Momentum pillar REMOVED from the fundamental composite.** It double-counted
  the Tecnico lens and was counter-predictive at 1y; the IC study drove its
  removal (`score_service.PILLAR_WEIGHTS` — 5 pure-fundamental pillars now).
- **Net/operating-margin LEVELS demoted in the profitability pillar.** The IC
  study found `net_margin` at **−0.047 @252d** — counter-predictive at 1y. The
  validated re-tune promoted `gross_margin` (0.14→0.30) and `roa` (0.18→0.26),
  flipping the pillar's 1y IC positive. (`entry_ic_report --validate-prof-retune`.)
- **Trade-playbook `tbs%` base rate DATA-REJECTED for Probabilità.** Measured as
  a candidate (C2, 2026-05), it clustered ~18–23% (NARROWER spread than `absHit`,
  range 5.8 vs 8.7) and was undefined for 6/14 detectors with no structural
  level. Rejected; `absHit%` stayed.
- **The single `confidence` score was shown ~FLAT vs realised outcome**
  (hit-rate by band: <60→51%, 60–70→49%, 70–80→49%, 80–90→52%, 90+→54%). That
  flatness is *why* it was split into Forza + Probabilità.

When in doubt, do what these did: **keep the current params and reject the
candidate.**

---

## 2. Family A — fundamental pillar weights + ramp anchors

**What's tunable.** `score_service.PILLAR_WEIGHTS` (5 pillar weights summing to
1.0) and the per-component `_ramp3` anchors (`abs_full/abs_half/abs_zero`, and
the `rel_*_pp` sector-relative anchors) inside `_profitability`, `_growth`,
`_value`, `_sustainability`.

**What to run.**
```bash
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.entry_ic_report \
  --validate-prof-retune --us-only      # profitability pillar: OLD vs NEW weights
# also available: --validate-retune (momentum proxy), --validate-fundamentals,
#                 --validate-xs (absolute vs sector-relative ranking)
```
The validator builds a percentile-normalised composite of the pillar's
components, computes per-date rank-IC at each horizon (5/21/63/252d), and prints
an **`OLD` / `NEW` / `NEW-OLD`** table. Rank-IC is invariant to the monotone
percentile transform, so the **weighting** drives the delta.

**What gates it.** The **`NEW-OLD` dIC at the slow horizon (252d)** must be
clearly positive on the held-out stocks. Read the `NEW-OLD` row; feed the two IC
numbers into `passes_oos_gate(old_ic, new_ic, min_rel_improvement=0.05)`.

**Threshold.** As a rule of thumb in single-name equity: |IC| ~0.03–0.05 is
useful, ~0.05–0.08 strong, >0.10 rare/suspicious; IR > 0.5 means the edge is
stable across regimes. A retune that improves IC at 252d **and doesn't regress
the shorter horizons** passes. A retune that helps 21d but **hurts 252d** for a
fundamental pillar is a reject (wrong horizon).

**Anti-overfit notes specific to A.** Anchors are economic thresholds (ROE ≥20%
→ full), not curve-fit knobs — move them only with a peer-distribution reason.
Keep the absolute floor in the 50/50 sector blend (`_BLEND_ALPHA = 0.5`) so a
"least-sick-patient-in-a-hospice" name can't score high on relative alone.

---

## 3. Family B — signal per-factor curve anchors + `score_v2` delta

**What's tunable.** The per-detector `concave(x, anchors)` / `log_saturate(x,
ceil)` anchor tuples in each detector (the raw values mapping to contributions
0.45 / 0.75 / 0.88), and the global `score_v2` soft-min `delta`
(`base._V2_DELTA = 0.12`) + guardrail (`0.99`).

**What to run.**
```bash
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.signal_factor_outcomes
# per-FACTOR bucketed hit-rate + SUGGESTED ANCHORS (raw value where the realised
# hit-rate crosses 52/56/60% → the 0.45/0.75/0.88 breakpoints).

cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.signal_detector_outcomes
# per-DETECTOR base-rate spread + the "is current confidence predictive?" band
# table (the conjunction carries edge the marginals don't).
```

**What gates it.**
- **Anchors:** the factor's bucketed hit-rate must be **monotonic in the raw
  value** (the harness prints a `monotonic(...)` flag). Place anchors at the
  empirically-grounded crossings the harness suggests — *not* at the 90th
  percentile of rarity. **Forza legitimately rises with magnitude even for
  mean-reverting factors** (a big gap IS a strong pattern); the
  mean-reversion is carried by Probabilità (Family C), not by flattening Forza.
- **`score_v2` delta:** changing it reshapes the whole Forza distribution. Gate
  on the **distribution-shift integration test** (fewer ≥85 than the old
  `confidence`, emission floor `signal_min_confidence = 60` not silently moved)
  plus the detector base-rate spread staying informative.

**Threshold.** Anchors: ship only if the new curve is monotonic AND the detector
the factor feeds keeps or improves its base-rate spread. Delta: ship only if the
Forza distribution stays well-spread (no re-pinning at the top) and no
previously-emitting signal is silently dropped by the reshape.

**⚠️ Units trap (read the factor formula).** Anchors must be in the **units of
the value PASSED TO THE CURVE**, not the raw indicator. E.g. a factor computed as
`clamp01((ADX-25)/75)` passes a **0..1** value to `concave`, so its anchors are
in 0..1 — **not** raw ADX points. Getting this wrong silently mis-scales the
curve.

---

## 4. Family C — Probabilità base rates / calibration model

**What's tunable.** The committed artifact `app/data/signal_calibration.json`:
the per-detector `base_rate` (absolute directional hit-rate, the "di
accadimento" probability) and the optional `factor_adjustments` (bounded ±~8pt
per-factor nudges). Probabilità = `clamp(base_rate + Σ adj_k, [5, 95])` via
`base.probability_from_factors`.

**What to run.**
```bash
# (a) Regenerate the FLAT base-rate artifact (the current v1 model):
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.signal_detector_outcomes --emit-map
# writes app/data/signal_calibration.json from per-detector absHit% base rates.

# (b) Fit + OOS-VALIDATE an UPGRADE candidate (isotonic / L2 logistic) and only
#     adopt it if it clears the gate on BOTH the disjoint-stock and temporal split:
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.fit_signal_calibration --emit-map
# --emit-map writes the upgraded artifact ONLY IF the model is ADOPTED.
```

**What gates it.** **OOS Brier score (lower is better)** of the candidate
calibration vs the baseline (the per-detector train-set base rate — i.e. exactly
what the current artifact encodes), measured on **disjoint test stocks AND a
temporal holdout**. `fit_signal_calibration` reports Brier + log-loss + a
reliability table and **adopts the model only if it clears the threshold on both
splits** — otherwise it leaves the artifact untouched. This is the same
honesty-over-sophistication bar that data-rejected `tbs%`.

**Threshold.** Candidate Brier must be **clearly below** baseline Brier on both
held-out splits: `passes_oos_gate(baseline_brier, candidate_brier,
min_rel_improvement=0.05, lower_is_better=True)`. A flat or noisy Brier
improvement is a reject — Probabilità stays on the simpler base-rate model.

**Anti-overfit notes specific to C.** Single-name technical hit-rates hover
~45–55% (near coin-flip), so the base rate dominates and per-factor adjustments
are bounded small on purpose. Regime-conditioning and multivariate calibration
are future work; do not add them without an OOS-Brier win on both splits.

---

## 5. The orchestrator: `app.scripts.retune`

A **read-only** reporting tool that prints a **PROPOSAL DIFF** — current params
vs a candidate + the OOS gate verdict — for a human to review. It does **NOT**
auto-apply, regenerate artifacts, or commit. It reuses the harnesses above; it
never re-implements their IC/outcome math.

```bash
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.retune
  --family {pillars,signals,probability,all}   # default: all
  --run                          # re-run the underlying harness live (slow, reads DB)
  --min-rel-improvement 0.05     # relative OOS improvement required to PASS
  --candidate-calibration PATH   # diff a candidate signal_calibration.json (family C)
  --json                         # machine-readable proposal
```

For each family it prints: the **param table** (current vs candidate, changed
rows marked `*`), the **OOS gate metric** (name + direction), the baseline and
candidate metric on the **test** stocks, and the **VERDICT** (`PASS` = a
candidate for review, `FAIL` = reject). Until a real measured candidate is wired
in, the metric is a placeholder `NaN` and every family reports **`FAIL —
unmeasured`** — by design: *an unvalidated change must never pass.*

The gate itself (`passes_oos_gate`, unit-tested in `tests/test_retune_gate.py`):

```python
passes_oos_gate(baseline_metric, candidate_metric,
                *, min_rel_improvement, lower_is_better=False) -> bool
```
- higher-is-better default (rank-IC); `lower_is_better=True` for Brier.
- **NaN/inf → False** (an unmeasurable result is never "clearly better").
- **flat / worse → False.** Boundary is inclusive (float-tolerant).
- zero-baseline or a sign change → falls back to an **absolute-points** bar AND
  requires the correct side of zero (so a −0.01→+0.01 flip isn't a "200% win").
- a **negative** `min_rel_improvement` is treated as its absolute value (it can
  never invert the rule into "accept anything").

---

## 6. Versioning & commit discipline (after a proposal PASSES review)

A passing gate is a **candidate**, not an approval. To ship it:

1. **Apply by hand.** Edit the param in source (`PILLAR_WEIGHTS`, the ramp/curve
   anchors, `_V2_DELTA`) OR regenerate the artifact with the proper harness
   (`--emit-map`). The orchestrator never does this for you.
2. **Re-run the full suite** (`cd backend && ./.venv/Scripts/python.exe -m
   pytest tests/ -x -q`) and the **`test_ranking_regression.py`** non-regression
   gate where the change moves the composite (freeze a new baseline only after
   it's green).
3. **Commit the regenerated artifact** (e.g. `app/data/signal_calibration.json`)
   **together with the code change**, and put the **OOS metrics in the commit
   message** — the baseline→candidate numbers on the held-out split, and which
   split(s) it cleared. The artifact is the versioned record of the model; the
   message is the versioned record of *why we believed it.* Example:
   ```
   feat(calibration): adopt isotonic Probabilità map (OOS Brier 0.2487→0.2361
   disjoint-stock, 0.2502→0.2399 temporal; both clear the +5% gate)
   ```
4. **If the change touches scoring output the UI reads**, follow the post-commit
   hygiene in `CLAUDE.md` (rebuild `frontend/dist`, restart uvicorn, verify
   `/api/health`).
5. **If the gate did NOT clearly pass — do nothing.** Record the rejection (a
   one-line note in the relevant script's docstring, as we did for `tbs%`) so we
   don't re-litigate it next quarter. Keeping the current params is a valid,
   common, and correct outcome of this loop.

---

## 7. One-pass checklist

- [ ] Stop uvicorn first if running a harness that needs the DB (sole SQLite
      writer → avoids "database is locked").
- [ ] Pick the family; run its harness (§2/§3/§4) with a **disjoint-stock**
      (and, for C, **temporal**) split.
- [ ] Read the OOS metric on the **test** stocks (not train, not pooled).
- [ ] `app.scripts.retune --family <f>` for the proposal diff + gate verdict.
- [ ] `passes_oos_gate(...)` is `True` on the test split? If not → **reject,
      keep current params, record why.**
- [ ] If `True`: apply by hand → full suite + ranking-regression green →
      commit code + regenerated artifact with **OOS metrics in the message**.
- [ ] FE-visible? Rebuild `dist` + restart backend + verify health.
