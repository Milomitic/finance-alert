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
// Empirically calibrated against a manual run on 2026-05-13 (1097 stocks):
// the live `done/elapsed` rate settled at ~4 stocks/sec, NOT the 6 we were
// using as the prior. The toast shows the baseline only during the first
// ~1s before live rate takes over, so an honest baseline avoids flashing
// an over-optimistic ETA that immediately corrects upward.
const BASELINE_FETCHING_INCREMENTAL_BARS_PER_SEC = 4.5;
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
  // High-level step grouping for the toast's "Passo X di N" indicator.
  // Mutually-exclusive sub-phases share one logical step (e.g. backfill
  // and incremental are two paths through the same "Download" step;
  // scoring and scoring_recompute belong to two different steps because
  // they actually run sequentially in the post-scan flow).
  //
  // `durationHintSec` ranges calibrated against real scan_runs on
  // 2026-05-13 (catalog = 1097 stocks). The lower bound is "best case
  // warm path"; the upper is "typical worst case" (mostly incremental
  // with a handful of backfills). A truly cold-DB first scan with full
  // 10y backfill across the catalog runs ~18min — outside the typical
  // hint, kept that way so the bar doesn't flash 18min on every run.
  steps: [
    {
      label: "Preparazione catalogo",
      phases: [
        "fetching:loading_catalog",
        "fetching:checking_staleness",
        "fetching:planning",
      ],
      // Catalog SELECT (~50ms) + bulk staleness GROUP BY on 1097 stocks
      // (~200ms) + commit. Sub-second on warm DB; 1-5s gives slack for
      // a cold-cache first SELECT.
      durationHintSec: [1, 5],
    },
    {
      label: "Download dati di mercato",
      phases: ["fetching:backfill", "fetching:incremental", "fetching"],
      // 1097 stocks ÷ ~4 stocks/sec live rate (incremental) = ~275s
      // floor; with a few backfill chunks (each ~20s for 20 stocks at
      // 1 stock/sec) we land in the 4-12 min window. Real run-97 took
      // ~10min, run-96 ~5min — this range covers both.
      durationHintSec: [180, 720],
    },
    {
      label: "Valutazione regole",
      phases: ["evaluating:loading_rules", "evaluating:scoring", "evaluating"],
      // scan_universe ~60 stocks/sec → 1097/60 ≈ 18s + ~2s rule load.
      // Slower on cold cache where rule eval triggers fundamentals
      // lookups; broaden upper to 40s.
      durationHintSec: [10, 40],
    },
    {
      label: "Snapshot mercato",
      phases: ["evaluating:market_snapshot"],
      // recompute_snapshot is one synchronous compute over the
      // fundamentals L1/L2 cache. Warm: 3-10s. Cold (post-restart,
      // first scan): 30-90s due to yfinance retries inside _load_metrics.
      durationHintSec: [3, 60],
    },
    {
      label: "Statistiche settori e score",
      phases: [
        "evaluating:sector_stats",
        "evaluating:scoring_recompute",
        "evaluating:persisting",
      ],
      // sector_stats prepass (cached: <1s, cold: 5-30s) + recompute_all
      // per-stock loop (1097/80 = 14s baseline, slower on cold cache
      // when bulk_load_recent_bars misses). Combined typical 15-90s.
      durationHintSec: [15, 90],
    },
    {
      label: "Price-target alert",
      phases: ["evaluating:price_alerts"],
      // evaluate_all loops over price-target rules — small list, no
      // network calls (uses cached quotes). Almost always sub-2s; 5s
      // upper covers a one-off slow query.
      durationHintSec: [1, 5],
    },
  ],
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
