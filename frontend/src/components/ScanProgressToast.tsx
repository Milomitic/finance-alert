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
 * Sub-phases (May 2026 taxonomy, expanded mid-May):
 *   fetching:loading_catalog    — SELECT the universe of stocks
 *   fetching:checking_staleness — bulk latest-bar lookup, decides
 *                                 backfill-vs-incremental split per stock
 *   fetching:planning           — legacy umbrella (back-compat; renamed
 *                                 to loading_catalog + checking_staleness
 *                                 in the May UX pass since flashing one
 *                                 generic label was too brief to read)
 *   fetching:backfill           — chunk loop, period="10y" (slow path)
 *   fetching:incremental        — chunk loop, period="1mo" (fast path)
 *   evaluating:loading_rules    — between fetch end and first scoring tick
 *   evaluating:scoring          — main per-stock rule eval loop
 *   evaluating:market_snapshot  — breadth + leaders snapshot refresh
 *   evaluating:sector_stats     — sector_stats pre-pass for the score
 *                                 recompute (announced separately so the
 *                                 user knows the "sector data" prep step)
 *   evaluating:scoring_recompute — per-stock composite recompute
 *   evaluating:price_alerts     — price-target alert evaluation pass
 *   evaluating:persisting       — legacy umbrella (back-compat)
 *
 * The bare "fetching" / "evaluating" values are preserved for back-compat
 * with rows written before sub-phases were introduced. Empirical baseline
 * rates per sub-phase prime the initial ETA — the live rate (done/elapsed)
 * takes over once a few heartbeats have arrived.
 */

const BASELINE_FETCHING_PLANNING_BARS_PER_SEC = 50.0;
const BASELINE_FETCHING_LOADING_CATALOG_BARS_PER_SEC = 200.0;
const BASELINE_FETCHING_CHECKING_STALENESS_BARS_PER_SEC = 200.0;
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
      // Prep sub-phases (split out from the old `fetching:planning` umbrella
      // so the user can read each step before chunks start scrolling)
      case "fetching:loading_catalog":
        return "Caricamento elenco stock dal catalogo";
      case "fetching:checking_staleness":
        return "Verifica freschezza barre OHLCV";
      case "fetching:planning":
        return "Preparazione: catalogo e date storiche";
      // Chunk loop
      case "fetching:backfill":
        return "Backfill storico (10 anni di barre)";
      case "fetching:incremental":
        return "Aggiornamento incrementale (ultimo mese)";
      case "fetching":
        return "Scaricamento dati di mercato";
      // Evaluation phase
      case "evaluating:loading_rules":
        return "Caricamento regole attive";
      case "evaluating:scoring":
        return "Valutazione regole per stock";
      // Post-evaluation persisting sub-phases (split out from
      // `evaluating:persisting` so the user sees WHICH step is running
      // — sector_stats prep is especially worth announcing because it
      // can take 5-20s on cold caches)
      case "evaluating:market_snapshot":
        return "Aggiornamento snapshot di mercato";
      case "evaluating:sector_stats":
        return "Pre-calcolo statistiche settoriali";
      case "evaluating:scoring_recompute":
        return "Ricalcolo score composito per stock";
      case "evaluating:price_alerts":
        return "Valutazione price-target alert";
      case "evaluating:persisting":
        return "Finalizzazione: snapshot · score · price alert";
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
      case "fetching:loading_catalog":
        return BASELINE_FETCHING_LOADING_CATALOG_BARS_PER_SEC;
      case "fetching:checking_staleness":
        return BASELINE_FETCHING_CHECKING_STALENESS_BARS_PER_SEC;
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
      // Post-scoring sub-phases — the bar is already pinned at 100%
      // (progress_done == progress_total from the end of scoring). The
      // baseline is only consulted when `remaining > 0`, which doesn't
      // happen here — but we provide values anyway for safety.
      case "evaluating:market_snapshot":
      case "evaluating:sector_stats":
      case "evaluating:scoring_recompute":
      case "evaluating:price_alerts":
      case "evaluating:persisting":
        return 1;
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
