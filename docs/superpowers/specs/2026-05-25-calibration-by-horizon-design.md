# Calibration by Horizon — Design

**Goal:** Add a horizon dimension to outcome calibration and seed the curve
from a backtest so the panel is informative immediately (live calibration
matures only after the forward window elapses).

**Status:** Implemented 2026-05-25.

## What
- `compute_calibration` now also buckets by **horizon** (`by_horizon`), reading
  `snapshot.horizon` (the shared attribute from Phase 1). Live data; matures
  over the forward window.
- `load_calibration_seed()` reads `app/data/calibration_seed.json` — a backtest-
  derived reference (forward 20d, direction-adjusted) by horizon, by confidence,
  and by confidence x horizon. The `/calibration` endpoint returns it as
  `backtest_seed` so the Settings panel shows the curve NOW.
- Panel: a live "Per orizzonte" table + a "Riferimento backtest" section
  (confidence / horizon / nature).

## Seed findings (backtest, forward 20d, direction-adjusted)
- by horizon hit-rate / mean: short 49.4% / -0.11%, medium 49.5% / -0.03%,
  **long 52.5% / +0.36%** -> long is the edge (consistent with the playbook +
  multi-horizon backtests).
- by confidence is monotonic: 60-69 -0.21% -> 90-100 +0.35% (hit 49.8% ->
  51.8%) -> the raw confidence score IS meaningfully calibrated.
- confidence x horizon reveals the interaction: **90-100|long = 53.2% / +0.76%**
  (best), but **90-100|short = 49.1% / -0.47%** -> high confidence only pays on
  the long horizon; a high-confidence short signal is still a coin flip with
  negative drift. This interaction is exactly why splitting by horizon matters.

## Caveats / follow-up
- Backtest seed = prior; live `by_horizon` refines it over time. Survivorship +
  no costs apply to the seed.
- Loop-closing (a "calibrated probability" shown next to raw confidence, derived
  from this curve) is a later step.
