# KPI Collection & Engine Monitoring — Plan

**Goal:** Predispose systematic KPI capture + monitoring so the engines (signal,
technical score, confluence, playbook, calibration) can be improved continuously
from data, and "important signals" (edge erosion, data outages, calibration
drift, anomalies) get intercepted early.

**Guiding principle:** you cannot analyze a trend you did not record. Today
metrics are computed on demand and discarded. The urgent groundwork is to start
PERSISTING a time series now; the dashboards + alerts come later.

## 1. KPI taxonomy (what to measure)
- **Scan health:** duration; stocks scanned / skipped / failed; OHLCV fetch
  success rate; gate drop counts (regime, follow-through, recency, dedup);
  exceptions.
- **Signal production:** signals fired per scan by detector / tone / horizon /
  nature / confidence bucket; confidence distribution; per-detector fire rate
  (detect dead or flooding detectors).
- **Outcome / calibration (the gold loop):** realized directional hit-rate +
  forward return by detector / confidence / horizon / nature / multi-horizon,
  recorded as a ROLLING TIME SERIES (not a one-shot). Track calibration drift
  (nominal confidence vs realized hit-rate over time).
- **Confluence:** cluster count; multi-horizon rate; contested rate; strength
  distribution.
- **Playbook:** stop% distribution; R:R distribution; cap-bind rate (% stops
  floored / capped); TP-hit rate (from outcomes); horizon mix.
- **Data quality:** OHLCV staleness (% stale stocks); fundamentals cache
  hit/miss + freshness; upstream error rates by source (yfinance / finnhub /
  marketaux); L1/L2 hydration counts.
- **Technical score:** composite + sub-dimension distributions; posture mix;
  coverage (% stocks scored).

## 2. Collection + storage (the predisposition)
- **`kpi_snapshots` table** (append-only time series): `id, captured_at, kind
  (scan|daily_rollup|data_quality), scope (nullable: detector/horizon/...),
  metrics JSON`. Indexed on (kind, captured_at). Cheap, never mutated.
- **Per-scan capture:** hook into `scan_runner` (alongside the existing
  `ScanRun`) to write one `kind="scan"` row at scan end with the scan-health +
  signal-production counts (most are already computed in the scan loop).
- **Daily outcome rollup job (scheduler):** recompute the rolling calibration
  (now that forward windows mature day by day) + playbook/confluence aggregates,
  append `kind="daily_rollup"` rows. This turns the one-shot calibration into an
  accumulating history.
- **Reuse:** `ScanRun` (scan metrics), `data_source_metrics` (upstream health,
  already exists), `compute_calibration` (outcome) -> persist their outputs.

## 3. Monitoring + interception (later phases)
- **Surface:** a "Salute motori" panel (Settings or dashboard) with KPI
  sparklines + flags.
- **Anomaly rules (intercept "important signals"):**
  - a detector's rolling hit-rate drops below threshold -> edge eroding;
  - scan failure / data-staleness spike -> pipeline problem;
  - calibration drift (a confidence bucket's realized hit-rate diverges from
    nominal) -> recalibrate;
  - signal-volume anomaly (a detector stops firing or floods) -> investigate.
- Flags are advisory (human-in-the-loop), feeding the continuous-improvement loop.

## 4. Phasing
- **Phase A (predisposition - build NOW, small):** `kpi_snapshots` table +
  migration; per-scan capture; daily outcome-rollup job. Starts accumulating
  the time series immediately. ~No UI.
- **Phase B (later):** the "Salute motori" monitoring panel (trends + current
  flags) reading `kpi_snapshots`.
- **Phase C (later):** automated anomaly detection + optional notifications.

## Why Phase A first
History is only capturable forward. Every scan/day without `kpi_snapshots`
populated is permanently lost trend data. Phase A is cheap (one table + a hook +
a cron) and unblocks all future analysis; B/C are pure consumers of the data A
collects.
