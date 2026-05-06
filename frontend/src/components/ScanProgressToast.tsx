import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  StopCircle,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ScanStatusInfo } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useStopScan } from "@/hooks/useAlertMutations";
import { useScanStatus } from "@/hooks/useScanStatus";
import { cn } from "@/lib/utils";

/* ─── ScanProgressToast — global persistent scan progress notification ───── */
/* Floats bottom-right of the viewport. Mounted once globally (Layout) so it
 * survives route changes — the user can navigate around while a scan runs
 * and still see live progress.
 *
 * Lifecycle:
 *   1. Hidden when no scan has been triggered.
 *   2. Appears the moment a scan starts (poll observes `is_running=true`).
 *   3. Updates with phase + progress as the worker reports heartbeats.
 *   4. Stays for 30s AFTER `completed_at` so the user sees the success/fail
 *      summary even if they were on a different tab during the run.
 *   5. Auto-dismisses after that 30s window. Manual dismiss any time by
 *      clicking the close button OR clicking on the toast body itself
 *      (the entire surface is a "got it" affordance).
 *
 * Why this and not a card on the page:
 *   - The dashboard is a snapshot surface. A card that grows/shrinks based
 *     on transient process state was visually distracting.
 *   - Toast position is universal — works on AlertsPage, StockDetail, etc.
 *   - "Persists 30s after completion" gives the user the receipt of a scan
 *     they triggered without forcing them to stay on a specific page.
 *
 * Manual dismissal is tracked PER `last_run_id` so that:
 *   - Dismissing a completed scan's toast doesn't suppress the NEXT scan.
 *   - Dismissing a running scan's toast suppresses it for that whole run
 *     (we don't pop it back up if they accidentally click away).
 */

const POST_COMPLETION_VISIBLE_MS = 30_000;
const TICK_MS = 1_000;

/* Empirical baseline rates for the initial ETA — measured across recent
 * production scans on the dev box. Used as priors only: as soon as the
 * actual run produces a few heartbeats, the live (done/elapsed) rate
 * takes over. This means the user sees a credible ETA from second one,
 * not a "—" or null. */
const BASELINE_FETCHING_BARS_PER_SEC = 4.0;    // ~4 stocks/sec while fetching OHLCV from yfinance (with healthy rate)
const BASELINE_EVALUATING_BARS_PER_SEC = 60.0; // ~60 stocks/sec while evaluating rules (CPU-bound, no I/O)
/* When neither phase is reported (data not yet flowed), assume the slower
 * fetching phase — better to overestimate than to under-promise. */
const BASELINE_OVERALL_BARS_PER_SEC = BASELINE_FETCHING_BARS_PER_SEC;

function formatSecs(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r === 0 ? `${m}m` : `${m}m ${r}s`;
}

function elapsedSeconds(status: ScanStatusInfo, nowMs: number): number {
  if (!status.started_at) return 0;
  const startedMs = new Date(status.started_at).getTime();
  if (status.completed_at) {
    return Math.max(0, (new Date(status.completed_at).getTime() - startedMs) / 1000);
  }
  if (status.is_stale && status.last_progress_at) {
    return Math.max(
      0,
      (new Date(status.last_progress_at).getTime() - startedMs) / 1000,
    );
  }
  return Math.max(0, (nowMs - startedMs) / 1000);
}

/** ETA in seconds remaining. Three tiers of estimate, picked in order:
 *
 *   1. Live rate from actual progress: `done / elapsed` — kicks in as soon
 *      as the worker has reported ≥1 heartbeat AND ≥1 second of elapsed
 *      time.
 *   2. Baseline rate by phase: fixed prior (~4 stocks/sec for fetching,
 *      ~60 for evaluating) using `progress_total` as the denominator.
 *      Used during the first second or before the first heartbeat — the
 *      previous version returned null here, leading to a confusing
 *      "no ETA" state for the first few seconds of every scan.
 *   3. null only when even `progress_total` isn't known yet (theoretical
 *      edge case — backend reports total before the first stock is
 *      processed).
 */
function estimateEtaSec(status: ScanStatusInfo, elapsed: number): number | null {
  const total = status.progress_total;
  const done = status.progress_done;
  if (total <= 0) return null;
  const remaining = Math.max(0, total - done);
  if (remaining <= 0) return 0;

  // Tier 1: live rate, only credible after ~1 second + ≥1 stock done.
  if (done > 0 && elapsed >= 1) {
    const rate = done / elapsed;
    if (rate > 0) return remaining / rate;
  }

  // Tier 2: baseline rate by phase. The numerator (remaining) is the
  // count of stocks still to process at the chosen baseline rate.
  const baseline =
    status.phase === "fetching"
      ? BASELINE_FETCHING_BARS_PER_SEC
      : status.phase === "evaluating"
        ? BASELINE_EVALUATING_BARS_PER_SEC
        : BASELINE_OVERALL_BARS_PER_SEC;
  return remaining / baseline;
}

export function ScanProgressToast() {
  const status = useScanStatus().data;
  const stopScan = useStopScan();

  // Tick once a second so:
  //   - the elapsed counter updates while running
  //   - the post-completion 30s window is enforced without polling
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  // Track which run_id the user has manually dismissed. Resets implicitly
  // when a new scan starts (its run_id won't match the dismissed one).
  const [dismissedRunId, setDismissedRunId] = useState<number | null>(null);

  // Have we ever observed this run_id? We use this to detect "the toast
  // appeared at least once, even briefly" — useful for the implicit
  // auto-dismiss to know we shouldn't replay the success banner if the
  // user was looking at it for the full 30s and is now on a fresh page.
  // Practically: the auto-dismiss is purely time-based (per completed_at),
  // so we don't actually need this beyond tracking dismissal. Keep simple.

  // Reset our seen set when the run_id changes (clean slate for new scans).
  const seenRunIdRef = useRef<number | null>(null);
  useEffect(() => {
    if (status?.last_run_id && status.last_run_id !== seenRunIdRef.current) {
      seenRunIdRef.current = status.last_run_id;
      // New run started → clear any prior dismissal so the toast pops up.
      // (No-op if dismissedRunId was null already.)
      setDismissedRunId((prev) =>
        prev !== null && prev !== status.last_run_id ? null : prev,
      );
    }
  }, [status?.last_run_id]);

  if (!status || !status.last_run_id) return null;
  if (dismissedRunId === status.last_run_id) return null;

  const isRunning = status.is_running;
  const completedAt = status.completed_at
    ? new Date(status.completed_at).getTime()
    : null;
  const sinceCompletion = completedAt ? now - completedAt : Infinity;
  const inPostCompletionWindow =
    !isRunning && completedAt && sinceCompletion < POST_COMPLETION_VISIBLE_MS;

  // Visibility: running OR within the post-completion window.
  if (!isRunning && !inPostCompletionWindow) return null;

  const elapsed = elapsedSeconds(status, now);
  const pct =
    status.progress_total > 0
      ? Math.round((status.progress_done / status.progress_total) * 100)
      : 0;
  const isStale = status.is_stale;
  // ETA shown to the user — credible from second one because we fall
  // back to per-phase baseline rates while the live rate isn't computable
  // yet. Only null in the rare window between scan-start and first
  // progress_total report from the backend.
  const etaSec =
    isRunning && !isStale ? estimateEtaSec(status, elapsed) : null;

  // Visual state per condition. Border + accent color drive the at-a-glance
  // read; iconography reinforces.
  const variant = isStale
    ? "stale"
    : isRunning
      ? "running"
      : status.status === "success"
        ? "success"
        : status.status === "failed"
          ? "failed"
          : "running";

  const headlineByVariant: Record<typeof variant, string> = {
    running: "Scan in corso",
    stale: "Scan bloccato",
    success: "Scan completato",
    failed: "Scan fallito",
  };

  const Icon =
    variant === "stale"
      ? AlertTriangle
      : variant === "running"
        ? Loader2
        : variant === "success"
          ? CheckCircle2
          : AlertCircle;

  // Fully opaque backgrounds (no `/N` modifiers, no backdrop-blur) so
  // the toast reads as a discrete surface even over a busy dashboard.
  // `bg-popover` instead of `bg-card` for the running variant: it's
  // already designed for floating overlays in our shadcn theme and
  // has stronger contrast against the page than `bg-card` (which can
  // match the dashboard cards too closely). For success/stale/failed
  // we use the same tinted-light fills paired with very dark dark-mode
  // counterparts (-900 instead of -950) so the colored background
  // reads cleanly against the foreground text in both color modes.
  const accentClass: Record<typeof variant, string> = {
    running: "border-primary bg-popover",
    stale: "border-amber-500 bg-amber-100 dark:bg-amber-900",
    success: "border-emerald-500 bg-emerald-100 dark:bg-emerald-900",
    failed: "border-rose-500 bg-rose-100 dark:bg-rose-900",
  };

  const iconClass: Record<typeof variant, string> = {
    running: "text-primary",
    stale: "text-amber-600 dark:text-amber-400",
    success: "text-emerald-600 dark:text-emerald-400",
    failed: "text-rose-600 dark:text-rose-400",
  };

  // Countdown shown to the user during post-completion window so the
  // auto-dismiss doesn't feel like a glitch. ~30s ticker.
  const dismissCountdown =
    inPostCompletionWindow && completedAt
      ? Math.max(
          0,
          Math.ceil((POST_COMPLETION_VISIBLE_MS - sinceCompletion) / 1000),
        )
      : null;

  const phaseLabel =
    status.phase === "fetching"
      ? "Scaricamento dati di mercato"
      : status.phase === "evaluating"
        ? "Valutazione regole"
        : null;

  const dismiss = () => setDismissedRunId(status.last_run_id);

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 z-50",
        "w-[min(28rem,calc(100vw-2rem))]",
        // Slide-up + fade entrance. Fragility: if the toast goes from
        // running → success the variant change keeps the same DOM node so
        // the entrance doesn't replay; that's intentional — we don't want
        // the toast to "jump" mid-scan.
        "animate-in fade-in slide-in-from-bottom-4 duration-200",
      )}
      role="status"
      aria-live="polite"
    >
      <div
        className={cn(
          "rounded-lg border-2 shadow-xl cursor-pointer",
          "transition-shadow hover:shadow-2xl",
          accentClass[variant],
        )}
        onClick={dismiss}
        title="Clicca per chiudere"
      >
        {/* Header row — icon + headline + close button */}
        <div className="flex items-start gap-3 p-3">
          <Icon
            className={cn(
              "h-5 w-5 shrink-0 mt-0.5",
              iconClass[variant],
              variant === "running" && "animate-spin",
            )}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-sm font-semibold leading-tight">
                {headlineByVariant[variant]}
              </span>
              <span
                className="text-[11px] text-muted-foreground tabular-nums"
                title="Tempo trascorso dall'avvio"
              >
                {formatSecs(elapsed)}
              </span>
              {etaSec != null && etaSec > 0 && (
                <span
                  className="text-[11px] text-muted-foreground tabular-nums"
                  title="Stima del tempo residuo. Calibrato sulla velocità misurata o, all'avvio, su un valore di riferimento per la fase corrente."
                >
                  · ETA ~{formatSecs(etaSec)}
                </span>
              )}
              {dismissCountdown != null && (
                <span
                  className="ml-auto text-[10px] uppercase tracking-wider text-muted-foreground/70 tabular-nums"
                  title="La notifica si chiuderà automaticamente"
                >
                  chiusura in {dismissCountdown}s
                </span>
              )}
            </div>
            {phaseLabel && variant === "running" && (
              <div className="text-[11px] text-muted-foreground mt-0.5">
                {phaseLabel}
              </div>
            )}
          </div>
          <button
            type="button"
            aria-label="Chiudi notifica"
            onClick={(e) => {
              e.stopPropagation();
              dismiss();
            }}
            className="shrink-0 inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-muted/60 hover:text-foreground transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Progress bar — only while running. Click on it shouldn't dismiss
            so the user can click "Stop" without losing the toast. */}
        {isRunning && status.progress_total > 0 && (
          <div
            className="px-3 pb-2 space-y-1"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between text-[11px] text-muted-foreground">
              <span className="tabular-nums">
                {status.progress_done.toLocaleString()} / {status.progress_total.toLocaleString()}
              </span>
              <span className="font-semibold tabular-nums">{pct}%</span>
            </div>
            <div className="relative h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={cn(
                  "h-full transition-all duration-500",
                  isStale ? "bg-amber-500/70" : "bg-primary",
                )}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}

        {/* Stale warning — explains why the worker is stuck */}
        {isStale && status.seconds_since_last_progress != null && (
          <div
            className="mx-3 mb-2 text-[11px] bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100 rounded px-2 py-1.5"
            onClick={(e) => e.stopPropagation()}
          >
            Nessun heartbeat da{" "}
            <strong className="tabular-nums">
              {formatSecs(status.seconds_since_last_progress)}
            </strong>
            . Premi <strong>Termina (forzato)</strong> per sbloccare.
          </div>
        )}

        {/* Counters strip — final summary on completion + during running */}
        {(status.stocks_scanned !== null || status.alerts_fired !== null) && (
          <div
            className="grid grid-cols-3 gap-1.5 px-3 pb-3 text-[11px]"
            onClick={(e) => e.stopPropagation()}
          >
            <CounterCell
              label="Scansionati"
              value={status.stocks_scanned ?? 0}
            />
            <CounterCell
              label="Saltati"
              value={status.stocks_skipped ?? 0}
            />
            <CounterCell
              label="Alert"
              value={status.alerts_fired ?? 0}
              highlight={(status.alerts_fired ?? 0) > 0}
            />
          </div>
        )}

        {/* Stop button while running — don't auto-dismiss when it's clicked */}
        {isRunning && (
          <div
            className="px-3 pb-3 flex justify-end"
            onClick={(e) => e.stopPropagation()}
          >
            <Button
              variant={isStale ? "default" : "outline"}
              size="sm"
              disabled={stopScan.isPending}
              onClick={() => stopScan.mutate()}
              className={cn(
                isStale &&
                  "bg-amber-600 hover:bg-amber-700 text-white border-amber-600",
              )}
            >
              <StopCircle className="h-3.5 w-3.5 mr-1" />
              {isStale ? "Termina (forzato)" : "Stop"}
            </Button>
          </div>
        )}

        {/* Failure message */}
        {status.error_message && !isRunning && (
          <div
            className="mx-3 mb-3 text-[11px] text-rose-700 dark:text-rose-300 bg-rose-100/70 dark:bg-rose-900/30 rounded px-2 py-1.5"
            onClick={(e) => e.stopPropagation()}
          >
            {status.error_message}
          </div>
        )}
      </div>
    </div>
  );
}

function CounterCell({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded px-2 py-1 text-center",
        highlight
          ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-900 dark:text-emerald-100"
          : "bg-muted/60",
      )}
    >
      <div className="uppercase tracking-wider text-[9px] text-muted-foreground/80">
        {label}
      </div>
      <div className="font-bold tabular-nums">{value}</div>
    </div>
  );
}
