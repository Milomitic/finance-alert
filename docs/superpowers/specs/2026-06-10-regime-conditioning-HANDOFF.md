# Regime conditioning (#8) — HANDOFF for tomorrow (paused 2026-06-10)

## Where we stopped
First **non-null** technical finding of the whole effort: detector
**`trend_pullback` has regime-dependent market-neutral skill.** Everything is
committed; two background jobs were stopped mid-flight (both cheap to re-run).

## The finding (fast 50-stock pass — `app/data/regime_conditioned_study_fast50.json`)
Metric = market-neutral hit (tone-signed forward excess over universe mean > 0),
so a regime Δ is conditional SKILL, not beta. Regime = close vs causal EMA200.

| detector | bull% | bear% | Δ | CIsep | OOS sign (train→hold) |
|---|---|---|---|---|---|
| **trend_pullback** | **45.9** | **55.4** | **−9.5** | **YES** | **same** (−10.6 → −7.6) |
| oversold_reversal | 51.5 | 47.9 | +3.6 | no | same |
| sr_flip | 49.2 | 52.6 | −3.4 | no | same |
| other 10 | — | — | <±3 | no | mostly FLIP |

Only `trend_pullback` clears all three gates (CI-separated **and** OOS-sign-stable
**and** |Δ| material). n_bull=3059, n_bear=1340.

**Mechanism (plausible, not yet confirmed):** a pullback dipping *below* EMA200 is
a deeper/more-stretched pullback → more mean-reversion fuel → bigger bounce. So
"works better in bear regime" is likely **pullback depth** in disguise. Today the
detector fires with ONE base rate regardless → a real mis-calibration to fix.

## Two gates that must BOTH pass before any production change
1. **300-stock confirmation** (robustness — was the 50-stock split driven by a few
   names?). Re-run:
   ```
   cd backend && PYTHONIOENCODING=utf-8 PYTHONPATH=. ./.venv/Scripts/python.exe -u \
     -m app.scripts.regime_conditioned_outcomes --sample 300 --step 5 --holdout-frac 0.30 \
     --out app/data/regime_conditioned_study_full300.json
   ```
   ⚠️ This is a ~40–60 min batch job (detect_signals replay is ~100–250 ms/window).
   Best run unattended / overnight. PASS = trend_pullback keeps Δ≈−7..−10pp, CIsep,
   OOS-stable on 300 names.
2. **Adversarial verification workflow** (methodology — look-ahead? multiple-testing?
   beta residual? boundary artifact?). It was launched (`regime-finding-verifier`,
   run `wf_da190221-326`) but not captured before pause. Re-launch the Workflow with
   that saved script, or rebuild: harness look-ahead audit + 4 skeptic lenses
   (multiple-testing / cross-sectional-concentration / economic-mechanism /
   beta-residual) + synthesis. Script saved at:
   `…/workflows/scripts/regime-finding-verifier-wf_da190221-326.js`

## If BOTH pass → implement (the first validated Probabilità change)
- Add per-regime base rates for `trend_pullback` to `app/data/signal_calibration.json`
  (e.g. `regime: {bull: {base_rate: 46}, bear: {base_rate: 55}}`), keeping the flat
  `base_rate` as fallback.
- Teach `calibration_map.probability()` to use the regime base rate when the snapshot
  carries the regime (the signal snapshot already can compute close-vs-EMA200 at fire
  time; wire it through). TDD the loader change.
- Surface nothing new in the UI initially; this just makes Probabilità regime-aware
  for trend_pullback. Restart backend, verify /api/health, full suite.
- If only the 300-run passes but the workflow flags a fatal methodology issue (or vice
  versa) → **ship the null**, document, do NOT change calibration.

## State / artifacts (all committed)
- Harness: `app/scripts/regime_conditioned_outcomes.py` (now has `--out`).
- Fast-50 result: `app/data/regime_conditioned_study_fast50.json` (+ a copy at
  `regime_conditioned_study.json`).
- Preliminary warehouse look (thin): `2026-06-09-regime-conditioning-preliminary.md`.
- Backend healthy on :8000; migrations at head; 861 tests green; nothing else pending.

## The bigger arc (context)
This is the payoff of the Engine-Quality block: the `signal_outcomes` warehouse +
honest market-neutral metric is exactly what let a real conditional-skill effect
surface after a long string of validated nulls (#4 sector-relative, confirmation,
multi-horizon-target). trend_pullback regime-conditioning is the first thing that
could *earn* a Probabilità change — pending the two gates above.
