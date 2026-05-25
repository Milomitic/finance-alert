# Trade Playbook v2 (volatility + horizon anchored) — Design

**Goal:** Replace the structural-only stop/target geometry (which produced
microscopic stops on retests and absurd/negative targets on wide stops) with
a volatility- and horizon-anchored model, validated by backtest.

**Status:** Implemented 2026-05-25.

## Problem (measured on 895 live alerts)
- Stop = `|entry - structural_invalidation|`, unbounded. 147/895 stops < 0.5%
  (retests: entry adjacent to the level), 200/895 > 15%, 18 short targets < 0.
- Forward-outcome backtest of the old geometry: NEGATIVE expectancy
  (-0.025R; short -0.44R, medium -0.15R, long +0.03R).

## Model (decisions agreed with user)
- **Stop = structural, floored at `floor*ATR` (no cap).** A too-tight retest
  stop is widened to a sane ATR multiple; a wide structural stop is KEPT
  (= thesis invalidation) and the position is sized down instead.
- **Horizon = 3 classes** from chain time-span (primary; <=7d short, <=35d
  medium, else long) + detector prior (fallback for same-day/mono chains).
- **Targets = R-multiple capped at `cap*ATR`**, clamped so a short can't
  "gain" >95%. R:R is the honest readout (drops <1 when the structural stop
  is wide — signals a mediocre setup rather than faking 2R).
- **Duration** derived from horizon; multipliers scale with it.
- **ATR** added to the snapshot (backend, `ctx.atr`); legacy alerts fall back
  to a 2%-of-price proxy.

## Validated parameters (backtest 2026-05-25)
Replay over the pool, train/test split on DISJOINT stocks, usability-
constrained to TP-hit >= 25% (rejecting the degenerate "never take profit"
grid optimum, which had TP-hit ~3% and rode mark-to-market drift).

| Horizon | floor*ATR | TP1 R | TP1 cap*ATR | hold | test expectancy |
|---|---|---|---|---|---|
| short  | 0.5 | 4.0 | 2.0  | ~30d | +0.011R |
| medium | 2.5 | 2.0 | 10.0 | ~60d | +0.039R |
| long   | 1.0 | 3.0 | 8.0  | ~90d | +0.093R |

(vs old structural-only, out-of-sample: -0.44 / -0.15 / +0.03R). TP2 is a
farther "runner" target (1.5x TP1 distance, capped), not separately validated.

## Files
- `app/signals/signal_scan_service.py` — `atr` into snapshot.
- `api/types.ts` — `SignalSnapshot.atr`.
- `lib/tradePlaybook.ts` — full rewrite (horizon classify + floored stop +
  capped targets + derived duration + ATR fallback + side self-correction).
- `components/PlaybookView.tsx` — surface horizon.
- Data: one-off ATR backfill into existing active snapshots.

## Known characteristics / follow-ups
- Wide-structural-stop trend signals (trend_pullback/high52 vs far EMA200)
  keep their wide stop -> tiny position -> TP1 R:R can be < 1 (honest, by the
  floor-only choice). Optional: revisit a stop cap for the wide tail.
- Span can downgrade a strong-prior trend signal to "short" if its cross is
  recent. Faithful to the validated model; optional: clamp span within +/-1
  class of the detector prior, then re-validate.
