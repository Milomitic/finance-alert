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
import { cn } from "@/lib/utils";

/* ─── RunProgressToast — generic persistent progress notification ────────── */
/* Used by BOTH the alert-scan and the score-recompute flows. The backend
 * stores both kinds of run in the same `scan_runs` table (discriminated by
 * a `kind` column added in 6ed5a4d41b17). The UI surface is identical —
 * heartbeat, stale detection, post-completion 30s window, cooperative cancel.
 * Per-kind differences (headline copy, phase labels, counter labels) are
 * injected via the `labels` prop so this file owns the visual contract once.
 *
 * Lifecycle:
 *   1. Hidden when no run has been triggered.
 *   2. Appears the moment a run starts (poll observes `is_running=true`).
 *   3. Updates with phase + progress as the worker reports heartbeats.
 *   4. Stays for 30s AFTER `completed_at` so the user sees the success/fail
 *      summary even if they were on a different tab during the run.
 *   5. Auto-dismisses after that 30s window. Manual dismiss any time by
 *      clicking the close button OR clicking on the toast body itself.
 *
 * Manual dismissal is tracked PER `last_run_id` so that:
 *   - Dismissing a completed run's toast doesn't suppress the NEXT run.
 *   - Dismissing a running run's toast suppresses it for that whole run.
 */

const POST_COMPLETION_VISIBLE_MS = 30_000;
const TICK_MS = 1_000;

/** Per-kind copy + per-phase ETA priors. Each consumer (scan, recompute)
 *  supplies one of these so the generic toast can render the right labels. */
export interface RunToastLabels {
  /** Shown in the toast header per status variant. */
  headlines: {
    running: string;
    stale: string;
    success: string;
    failed: string;
  };
  /** Human-friendly label for each phase the backend emits. Returning null
   *  hides the phase row (e.g. for kinds with no sub-phases). */
  phaseLabel: (phase: string | null) => string | null;
  /** Counter strip labels — three cells. `value` extracts from the status row;
   *  return `null` to hide a cell entirely. */
  counters: {
    label: string;
    value: (s: ScanStatusInfo) => number | null;
    highlightWhenPositive?: boolean;
  }[];
  /** ETA prior in stocks-per-second per phase. Used during the first second
   *  of a run before the live `done/elapsed` rate is credible. */
  baselineRatePerSec: (phase: string | null) => number;
}

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

/** ETA seconds remaining. Live rate after ≥1s + ≥1 stock; otherwise the
 *  kind+phase baseline supplied by the consumer.
 *
 *  Critically takes `phaseElapsed` (not the run-total elapsed): each phase
 *  resets `progress_done` to 0, so blending the fetch's elapsed into the
 *  evaluate's rate would yield a phantom rate ~10× too low. The header still
 *  displays the run-total elapsed — only the ETA math wants per-phase. */
function estimateEtaSec(
  status: ScanStatusInfo,
  phaseElapsed: number,
  labels: RunToastLabels,
): number | null {
  const total = status.progress_total;
  const done = status.progress_done;
  if (total <= 0) return null;
  const remaining = Math.max(0, total - done);
  if (remaining <= 0) return 0;
  if (done > 0 && phaseElapsed >= 1) {
    const rate = done / phaseElapsed;
    if (rate > 0) return remaining / rate;
  }
  const baseline = labels.baselineRatePerSec(status.phase);
  return remaining / baseline;
}

interface Props {
  status: ScanStatusInfo | undefined;
  labels: RunToastLabels;
  /** Stop the underlying run. Wired to the kind-specific mutation by the
   *  wrapper component. `null` means stop isn't supported for this kind. */
  onStop?: () => void;
  isStopping?: boolean;
}

export function RunProgressToast({ status, labels, onStop, isStopping }: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  const [dismissedRunId, setDismissedRunId] = useState<number | null>(null);
  const seenRunIdRef = useRef<number | null>(null);
  useEffect(() => {
    if (status?.last_run_id && status.last_run_id !== seenRunIdRef.current) {
      seenRunIdRef.current = status.last_run_id;
      setDismissedRunId((prev) =>
        prev !== null && prev !== status.last_run_id ? null : prev,
      );
    }
  }, [status?.last_run_id]);

  // Track when the current phase started, so the ETA rate uses per-phase elapsed
  // instead of run-total elapsed. Without this, the rate during evaluating
  // includes the fetch time and yields a wildly inflated ETA. Reset on each
  // phase change (including sub-phase transitions like fetching:backfill →
  // fetching:incremental) so each phase's baseline gets a clean denominator.
  const phaseStartRef = useRef<{ phase: string | null; runId: number | null; startMs: number }>(
    { phase: null, runId: null, startMs: 0 },
  );
  useEffect(() => {
    if (!status) return;
    const phaseChanged = status.phase !== phaseStartRef.current.phase;
    const runChanged = status.last_run_id !== phaseStartRef.current.runId;
    if (phaseChanged || runChanged) {
      phaseStartRef.current = {
        phase: status.phase,
        runId: status.last_run_id,
        startMs: Date.now(),
      };
    }
  }, [status?.phase, status?.last_run_id]);

  if (!status || !status.last_run_id) return null;
  if (dismissedRunId === status.last_run_id) return null;

  const isRunning = status.is_running;
  const completedAt = status.completed_at
    ? new Date(status.completed_at).getTime()
    : null;
  const sinceCompletion = completedAt ? now - completedAt : Infinity;
  const inPostCompletionWindow =
    !isRunning && completedAt && sinceCompletion < POST_COMPLETION_VISIBLE_MS;

  if (!isRunning && !inPostCompletionWindow) return null;

  const elapsed = elapsedSeconds(status, now);
  const pct =
    status.progress_total > 0
      ? Math.round((status.progress_done / status.progress_total) * 100)
      : 0;
  const isStale = status.is_stale;
  const phaseElapsed =
    phaseStartRef.current.startMs > 0 &&
    phaseStartRef.current.phase === status.phase &&
    phaseStartRef.current.runId === status.last_run_id
      ? (now - phaseStartRef.current.startMs) / 1000
      : 0;
  const etaSec =
    isRunning && !isStale ? estimateEtaSec(status, phaseElapsed, labels) : null;

  const variant = isStale
    ? "stale"
    : isRunning
      ? "running"
      : status.status === "success"
        ? "success"
        : status.status === "failed"
          ? "failed"
          : "running";

  const Icon =
    variant === "stale"
      ? AlertTriangle
      : variant === "running"
        ? Loader2
        : variant === "success"
          ? CheckCircle2
          : AlertCircle;

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

  const dismissCountdown =
    inPostCompletionWindow && completedAt
      ? Math.max(
          0,
          Math.ceil((POST_COMPLETION_VISIBLE_MS - sinceCompletion) / 1000),
        )
      : null;

  const phaseLabel =
    variant === "running" ? labels.phaseLabel(status.phase) : null;
  // Live "what we're touching" chip — only meaningful while running and only
  // when the backend has populated the field. Stays hidden in the terminal
  // and stale variants so the row doesn't show a stale ticker from minutes ago.
  const currentTarget =
    variant === "running" && status.current_target ? status.current_target : null;

  const dismiss = () => setDismissedRunId(status.last_run_id);

  // Show the counter strip when any counter has a non-null value (i.e. the
  // backend has populated at least one of them, even mid-run).
  const counterValues = labels.counters.map((c) => ({
    ...c,
    value: c.value(status),
  }));
  const hasCounters = counterValues.some((c) => c.value !== null);

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 z-50",
        "w-[min(28rem,calc(100vw-2rem))]",
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
                {labels.headlines[variant]}
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
            {phaseLabel && (
              <div className="text-[11px] text-muted-foreground mt-0.5">
                {phaseLabel}
              </div>
            )}
            {currentTarget && (
              <div
                className="text-[10px] font-mono text-foreground/80 mt-0.5 truncate"
                title={currentTarget}
              >
                {currentTarget}
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

        {hasCounters && (
          <div
            className="grid grid-cols-3 gap-1.5 px-3 pb-3 text-[11px]"
            onClick={(e) => e.stopPropagation()}
          >
            {counterValues.map((c, idx) => (
              <CounterCell
                key={idx}
                label={c.label}
                value={c.value ?? 0}
                highlight={!!c.highlightWhenPositive && (c.value ?? 0) > 0}
              />
            ))}
          </div>
        )}

        {isRunning && onStop && (
          <div
            className="px-3 pb-3 flex justify-end"
            onClick={(e) => e.stopPropagation()}
          >
            <Button
              variant={isStale ? "default" : "outline"}
              size="sm"
              disabled={isStopping}
              onClick={onStop}
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
