import { useStopScan } from "@/hooks/useAlertMutations";
import { useScanStatus } from "@/hooks/useScanStatus";

import { RunProgressToast, type RunToastLabels } from "./RunProgressToast";

/* ─── ScanProgressToast — thin wrapper around the generic RunProgressToast ─
 *
 * Binds the alert-scan polling hook + stop mutation to the shared
 * presentation in RunProgressToast. Phase + counter labels are
 * scan-specific; everything else (lifecycle, heartbeat, stale handling,
 * post-completion window) lives in the generic component.
 *
 * Empirical baseline rates for the initial ETA — measured across recent
 * production scans on the dev box. Used as priors only: as soon as the
 * actual run produces a few heartbeats, the live (done/elapsed) rate
 * takes over.
 */

const BASELINE_FETCHING_BARS_PER_SEC = 4.0;
const BASELINE_EVALUATING_BARS_PER_SEC = 60.0;
const BASELINE_OVERALL_BARS_PER_SEC = BASELINE_FETCHING_BARS_PER_SEC;

const SCAN_LABELS: RunToastLabels = {
  headlines: {
    running: "Scan in corso",
    stale: "Scan bloccato",
    success: "Scan completato",
    failed: "Scan fallito",
  },
  phaseLabel: (phase) =>
    phase === "fetching"
      ? "Scaricamento dati di mercato"
      : phase === "evaluating"
        ? "Valutazione regole"
        : null,
  counters: [
    { label: "Scansionati", value: (s) => s.stocks_scanned },
    { label: "Saltati", value: (s) => s.stocks_skipped },
    {
      label: "Alert",
      value: (s) => s.alerts_fired,
      highlightWhenPositive: true,
    },
  ],
  baselineRatePerSec: (phase) =>
    phase === "fetching"
      ? BASELINE_FETCHING_BARS_PER_SEC
      : phase === "evaluating"
        ? BASELINE_EVALUATING_BARS_PER_SEC
        : BASELINE_OVERALL_BARS_PER_SEC,
};

export function ScanProgressToast() {
  const status = useScanStatus().data;
  const stopScan = useStopScan();
  return (
    <RunProgressToast
      status={status}
      labels={SCAN_LABELS}
      onStop={() => stopScan.mutate()}
      isStopping={stopScan.isPending}
    />
  );
}
