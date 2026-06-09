# Multi-horizon → wider TP2? Study findings (2026-06-09)

**Question (Phase 4, the one lever with a prior backtest claim):** the
`multi_horizon` confluence flag (prevailing-direction signals spanning ≥2
horizons) was noted to drift ~+0.8%/30d (bull). Does that justify a **wider
TP2** for multi-horizon bull setups?

**Method:** `app.scripts.multihorizon_outcomes` — replay `detect_signals()`
(no look-ahead), mark each match multi-horizon iff its tone side spans ≥2
detector horizons at that bar, and bucket the forward outcome by (tone,
multi_horizon): market-neutral **drift** excess, plus path-based **TP1-reach**
and **TP2-reach** (reached before the structural stop within the horizon).
Run: 60 stocks, step 25 → 28,129 signals.

| tone | multiHz | n | driftEx% | tp1% | tp2% |
|------|---------|---:|---------:|-----:|-----:|
| bull | False | 1,774 | −0.225 | 25.9 | 10.3 |
| bull | True  | 13,409 | **+0.129** | 23.8 | **9.7** |
| bear | False | 2,033 | −0.543 | 19.4 | 10.0 |
| bear | True  | 10,913 | +0.012 | 15.0 | 6.0 |

## Verdict — wider TP2 is NOT justified

- The **drift** claim is directionally corroborated: multi-horizon **bull** flips
  the mean forward excess from negative (−0.225%) to positive (+0.129%). It is a
  real but modest **directional / conviction** edge.
- **Reach is NOT improved** — the opposite, slightly: mh-bull reaches TP2 **9.7%**
  vs **10.3%** for mono, and TP1 23.8% vs 25.9%. A wider TP2 would be reached
  even *less* often → it would **worsen** expectancy, not improve it.
- A positive drift with no better reach means the favorable move is gradual /
  noisy, not a sharp run to a more ambitious target before the stop.

**Decision: do NOT widen TP2 (or any target) on `multi_horizon`.** The edge is
directional bias, not reach; targets stay as the backtest-validated geometry.

## What the data DOES support (kept minimal)

The mh-bull directional drift edge is a **conviction / selection** signal, not a
target-distance one. It is already used where it belongs: confluence ranking
puts bull multi-horizon clusters first (`confluence_service.compute_confluence`
sort key). No target, stop, Forza, or Probabilità change is warranted by this
study. (Stops were never in scope; they stay structural regardless.)

## Net: Phase 4 closes with no target change

Combined with the confirmation-count study (also null for scoring), the
evidence-based conclusion stands: **reinforcement is shown as context; scores,
stops and targets stay outcome-grounded.** No further scoring/target
intervention is justified by current data.

## Reproduce
```
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.multihorizon_outcomes --sample 60 --step 25 --window 400
```
