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
 * Sub-phases (since May 2026):
 *   fetching:planning      — universe load + bulk latest-bar lookup
 *   fetching:backfill      — chunk loop, period="10y" (slow path)
 *   fetching:incremental   — chunk loop, period="1mo" (fast path)
 *   evaluating:loading_rules — between fetch end and first scoring tick
 *   evaluating:scoring     — main per-stock rule eval loop
 *
 * The bare "fetching" / "evaluating" values are preserved for back-compat
 * with rows written before sub-phases were introduced. Empirical baseline
 * rates per sub-phase prime the initial ETA — the live rate (done/elapsed)
 * takes over once a few heartbeats have arrived.
 */

const BASELINE_FETCHING_PLANNING_BARS_PER_SEC = 50.0;
const BASELINE_FETCHING_BACKFILL_BARS_PER_SEC = 1.0;
const BASELINE_FETCHING_INCREMENTAL_BARS_PER_SEC = 6.0;
const BASELINE_FETCHING_BARS_PER_SEC = 4.0;
const BASELINE_EVALUATING_LOADING_BARS_PER_SEC = 80.0;
const BASELINE_EVALUATING_SCORING_BARS_PER_SEC = 60.0;
const BASELINE_OVERALL_BARS_PER_SEC = BASELINE_FETCHING_BARS_PER_SEC;

const SCAN_LABELS: RunToastLabels = {
  headlines: {
    running: "Scan in corso",
    stale: "Scan bloccato",
    success: "Scan completato",
    failed: "Scan fallito",
  },
  phaseLabel: (phase) => {
    switch (phase) {
      case "fetching:planning":
        return "Pianificazione: lettura universo e date storiche";
      case "fetching:backfill":
        return "Backfill storico (10 anni di barre)";
      case "fetching:incremental":
        return "Aggiornamento incrementale (ultimo mese)";
      case "fetching":
        return "Scaricamento dati di mercato";
      case "evaluating:loading_rules":
        return "Caricamento regole attive";
      case "evaluating:scoring":
        return "Valutazione regole per stock";
      case "evaluating":
        return "Valutazione regole";
      default:
        return null;
    }
  },
  counters: [
    { label: "Scansionati", value: (s) => s.stocks_scanned },
    { label: "Saltati", value: (s) => s.stocks_skipped },
    {
      label: "Alert",
      value: (s) => s.alerts_fired,
      highlightWhenPositive: true,
    },
  ],
  baselineRatePerSec: (phase) => {
    switch (phase) {
      case "fetching:planning":
        return BASELINE_FETCHING_PLANNING_BARS_PER_SEC;
      case "fetching:backfill":
        return BASELINE_FETCHING_BACKFILL_BARS_PER_SEC;
      case "fetching:incremental":
        return BASELINE_FETCHING_INCREMENTAL_BARS_PER_SEC;
      case "fetching":
        return BASELINE_FETCHING_BARS_PER_SEC;
      case "evaluating:loading_rules":
        return BASELINE_EVALUATING_LOADING_BARS_PER_SEC;
      case "evaluating:scoring":
      case "evaluating":
        return BASELINE_EVALUATING_SCORING_BARS_PER_SEC;
      default:
        return BASELINE_OVERALL_BARS_PER_SEC;
    }
  },
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
