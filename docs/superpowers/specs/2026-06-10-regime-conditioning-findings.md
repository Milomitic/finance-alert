# Regime conditioning (#8) — findings: trend_pullback REJECTED as artifact (2026-06-10)

## TL;DR
The trend_pullback "regime effect" (bull-regime 45.9% vs bear-regime 55.4%
market-neutral hit, CI-separated, OOS-stable) **passed all three credibility
gates and was still wrong**. Adversarial verification identified it as a
**tone-asymmetric metric artifact**, empirically confirmed. **No calibration
change.** The regime-conditioned Probabilità *mechanism* shipped (tested,
dormant) for any future finding that survives a skew-corrected study.

## The artifact, in three steps
1. **tone ≡ regime by construction.** trend_pullback's bear tone requires
   close < EMA50 < EMA200 — which IS the harness's "bear regime"
   (close ≤ EMA200) with probability ~1. The "regime split" was really the
   bull-tone vs bear-tone populations.
2. **The market-neutral hit metric is tone-ASYMMETRIC.** A bull hit = beating
   the equal-weight universe mean forward return; a bear hit = lagging it.
   Cross-sectional stock returns are right-skewed, so the EW mean sits above
   the median: with **zero skill**, P(beat mean) < 50% < P(lag mean).
3. **Empirical confirmation** (300 stocks, pure numpy on stored closes):
   P(beat EW mean) = **49.2% @5d, 48.4% @21d, 47.2% @63d**. At trend_pullback's
   63d horizon the zero-skill null is bull ≈ 47.2 / bear ≈ 52.8 → a structural
   **−5.6pp delta from nothing**. That's the dominant share of the observed
   −9.5pp; the residual ~−3.9pp is within what overlapping 63d windows +
   episode-clustered signals inflate (the nominal n≈3000/1300 grossly
   overstates the effective sample), and with tone ≡ regime it could not be
   attributed to "regime" anyway.

Why the gates failed to protect: **CI separation + OOS sign stability guard
against NOISE, not BIAS.** A structural artifact is permanent — it is stable
in every holdout and significant at any n. (The OOS gate even rewarded it.)

## Decisive experiment (median benchmark)
Re-ran the same study with hit = beat/lag the universe **MEDIAN** (tone-
symmetric by construction: exactly 50/50 under zero skill) — harness flag
`--benchmark median`, artifact `regime_conditioned_study_median50.json`.
**Result: see addendum below.**

## What shipped (mechanism, dormant)
Generic regime-conditioned Probabilità plumbing — byte-identical behavior
until a `regime` block exists in `signal_calibration.json` (none does):
- `SignalContext.regime` ("bull"/"bear" via close vs EMA200; None < 200 bars).
- `SignalMatch.regime` + snapshot `regime_at_fire` (audit trail).
- `CalibrationMap.regime_base_rate()` + `probability(..., regime=)` override.
- Runner stamps the regime and recomputes Probabilità ONLY for detectors with
  a regime record. TDD'd (4 tests incl. dormancy proof).

**Rule going forward:** any future regime block must come from a study using a
tone-SYMMETRIC outcome (median benchmark or forward-return percentile), pass
the CI/OOS gates AND an adversarial-verification pass. The mean-benchmark
artifact is now a known failure mode — check tone↔regime correlation first.

## Verification provenance
Workflow `regime-finding-verifier` (harness-lookahead audit + 4 skeptic
lenses). The **beta-residual** skeptic produced the kill (zero-skill null
matches the observation dead-center); the **harness audit** independently
flagged the tone↔regime mechanical correlation. Skew check reproduced the
predicted 47.2% @63d. The 300-stock confirmation run was cancelled — more
data cannot fix a structural bias.

## Addendum — median-benchmark result
(filled after the run)
