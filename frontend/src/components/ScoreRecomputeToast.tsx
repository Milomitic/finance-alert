import {
  useScoreRecomputeStatus,
  useStopScoreRecompute,
} from "@/hooks/useScoreRecompute";

import { RunProgressToast, type RunToastLabels } from "./RunProgressToast";

/* ─── ScoreRecomputeToast — mirror of ScanProgressToast for score recompute ─
 *
 * Binds the score-recompute polling hook + stop mutation to the shared
 * RunProgressToast presentation. The backend tracks both jobs via the same
 * `scan_runs` table (discriminated by `kind`), so the runtime contract is
 * identical — only the user-facing labels and ETA priors differ.
 *
 * Baseline rate for "scoring" phase: the per-stock compute_score path is
 * dominated by ~1ms-scale DB reads (closes + ohlcv_df) and a couple of
 * float-math passes; on a warm cache we're seeing ~100 stocks/sec in
 * dev, so 80 is a conservative prior. The sector_stats pre-pass can be
 * slow if delisted tickers force yfinance retries (each 4xx costs ~1s
 * with backoff), so its prior is the lower 20 — generous to avoid
 * showing "ETA 5s" when reality is 30s+.
 */

const BASELINE_SECTOR_STATS_BARS_PER_SEC = 20.0;
const BASELINE_SCORING_BARS_PER_SEC = 80.0;

const RECOMPUTE_LABELS: RunToastLabels = {
  headlines: {
    running: "Ricalcolo score in corso",
    stale: "Ricalcolo bloccato",
    success: "Ricalcolo completato",
    failed: "Ricalcolo fallito",
  },
  phaseLabel: (phase) =>
    phase === "sector_stats"
      ? "Calcolo mediane settoriali"
      : phase === "scoring"
        ? "Ricalcolo punteggi per stock"
        : null,
  counters: [
    {
      label: "Aggiornati",
      value: (s) => s.stocks_scanned,
      highlightWhenPositive: true,
    },
    { label: "Falliti", value: (s) => s.stocks_skipped },
    // Third cell repurposes the `alerts_fired` column for the count of
    // stocks SKIPPED by Strategy #2 (incremental-skip optimisation). The
    // backend's score_runner stores: stocks_scanned=ok, stocks_skipped=
    // failed, alerts_fired=skipped. See score_runner.py for the mapping
    // rationale (avoiding a schema migration for one new counter).
    { label: "Saltati", value: (s) => s.alerts_fired },
  ],
  baselineRatePerSec: (phase) =>
    phase === "sector_stats"
      ? BASELINE_SECTOR_STATS_BARS_PER_SEC
      : BASELINE_SCORING_BARS_PER_SEC,
};

export function ScoreRecomputeToast() {
  const status = useScoreRecomputeStatus().data;
  const stopRecompute = useStopScoreRecompute();
  return (
    <RunProgressToast
      status={status}
      labels={RECOMPUTE_LABELS}
      onStop={() => stopRecompute.mutate()}
      isStopping={stopRecompute.isPending}
    />
  );
}
