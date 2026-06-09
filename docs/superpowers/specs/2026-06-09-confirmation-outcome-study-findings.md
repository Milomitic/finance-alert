# Confirmation-count outcome study — findings (2026-06-09)

**Question (gates Phase 3c/3b/4):** do signals with MORE co-temporal
confirmations (the `confirmation_count` stamped by chain enrichment) resolve
their way MORE often?

**Method:** `app.scripts.confirmation_outcomes` — replays `detect_signals()`
over a trailing window (no look-ahead, same machinery as
`signal_detector_outcomes`) and buckets the realised forward outcome by
confirmation_count. Run: 40-stock sample, step 30, window 400 → **14,531
enrichable signals**. `absHit%` = close-to-close directional hit at the
detector's horizon; `tbs%` = TP1-before-stop (path-based, tradeable).

## Result — the hypothesis is REJECTED

Pooled across all technical detectors:

| #conf | n | absHit% | tbs% |
|------:|----:|--------:|-----:|
| 1 | 4258 | 49.9 | 21.5 |
| 2 | 5125 | 49.9 | 22.1 |
| 3 | 5148 | 49.1 | 20.5 |

Flat at ~50% — no monotonic lift, slightly *down* at 3. Per detector the signs
are mixed and unstable:

- **divergence family resolves WORSE with more confirmations**: macd_divergence
  51→47→42% absHit, rsi_divergence 48→49→40%, hidden_divergence 58→55→51%.
  Plausible read: a divergence surrounded by many co-temporal momentum events is
  already over-extended / late.
- flat/noisy: trend_pullback (54/51/56), gap_and_go (52/53/51), sr_flip
  (50/53/52), volume_breakout (52/52/52), chart_pattern (49/53/51).
- mildly UP only: oversold_reversal (42→47→47) — and still sub-50.
- `tbs%` (where a structural level exists) is likewise flat-to-down
  (volume_breakout 31→23→21).

## Decisions (evidence-based revision of the design)

1. **Phase 3c — NO `confirmation_count → Probabilità` adjustment.**
   `factor_adjustments` stays empty for confirmation_count. The data does not
   support it, and for divergence detectors a positive bonus would be
   *backwards*. `confirmation_count` remains **display-only** context (the
   Catena shows the co-temporal confirmations — useful for the user to read the
   setup — but it does not move the probability number).

2. **Phase 3b — NO per-alert `effective_forza` boost from confirmation/
   confluence count.** Same reason: inflating Forza on a non-predictive count
   would manufacture false conviction. (The de-correlated *cluster* strength
   from Phase 3a remains, but purely as a conservative aggregation/display — it
   makes no predictive claim and, by de-correlating, only ever *lowers* inflated
   confluence.)

3. **Phase 4 — targets/sizing key ONLY off the already-validated
   `multi_horizon` signal**, never raw confirmation/confluence count.
   `multi_horizon` is the one cross-signal feature with a prior backtest result
   (~+0.8%/30d bull drift, noted in confluence_service); any target widening
   must be gated on it and re-validated, and the stop stays structural.

## What this means for the user's request

The user's intuition — "more confirmations should reinforce the thesis" — is
**half right**: the confirmations are real and worth *showing* (Phase 1/2
deliver exactly that: the Catena now grows with EMA-reject / MACD / candle /
divergence / volume / lower-high steps across every technical detector). But
empirically they do **not** improve the win-rate, so letting them inflate
Forza / Probabilità / targets would mislead. The honest system shows the
context and keeps the score grounded in outcomes.

## Reproduce
```
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.confirmation_outcomes --sample 40 --step 30 --window 400
```
(Heavier samples are far slower because the Phase-2 extractors made
`detect_signals` costlier per call; 40×step-30 already yields ~14.5k signals,
ample for the verdict.)
