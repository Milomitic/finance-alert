import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  StopCircle,
} from "lucide-react";
import { useEffect, useState } from "react";

import type { ScanStatusInfo } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useStopScan } from "@/hooks/useAlertMutations";
import { cn } from "@/lib/utils";

interface Props {
  status: ScanStatusInfo | undefined;
  isFetching: boolean;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("it-IT", {
      dateStyle: "short",
      timeStyle: "medium",
    });
  } catch {
    return iso;
  }
}

/** Format a number of seconds as "Xm Ys" or "Xs" or "Xh Ym" depending on size. */
function formatSecs(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s}s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const r = s % 60;
    return r === 0 ? `${m}m` : `${m}m ${r}s`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

/**
 * Compute elapsed seconds since the scan started.
 *
 * For finished scans we use (completed_at - started_at), straightforward.
 * For running scans we tick once per second locally so the duration feels
 * live without forcing a polling refresh of the whole status object.
 *
 * **Crucially**: for stale (worker-died) scans we cap the elapsed at the
 * server-computed `seconds_since_last_progress + (last_progress - started)`
 * — otherwise the UI would happily count to "120m" against a worker that
 * actually died 2 min in, which is exactly the bug the user reported.
 */
function useElapsedSeconds(status: ScanStatusInfo | undefined): number {
  // Tick once a second only when running and not stale; otherwise once
  // is enough (the value won't change). This drives the live duration counter.
  const [now, setNow] = useState(() => Date.now());
  const isLive = !!status?.is_running && !status?.is_stale;
  useEffect(() => {
    if (!isLive) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isLive]);

  if (!status?.started_at) return 0;
  const startedMs = new Date(status.started_at).getTime();

  // Finished: use server-side end timestamp
  if (status.completed_at) {
    return Math.max(0, (new Date(status.completed_at).getTime() - startedMs) / 1000);
  }

  // Running but stale: cap at the last heartbeat so the counter doesn't run away
  if (status.is_stale && status.last_progress_at) {
    return Math.max(
      0,
      (new Date(status.last_progress_at).getTime() - startedMs) / 1000,
    );
  }

  // Running live: tick locally
  return Math.max(0, (now - startedMs) / 1000);
}

/**
 * ETA from elapsed/done ratio. Returns null when we don't have enough info
 * (no progress yet, or no total). Capped at the elapsed window — if the user
 * is staring at "ETA 12h" because progress is sluggish, that's a real signal,
 * but we don't bother showing ETA before any work has happened (would be
 * Infinity or noise).
 */
function computeEtaSec(
  elapsedSec: number,
  done: number,
  total: number,
): number | null {
  if (done <= 0 || total <= 0 || elapsedSec < 1) return null;
  const remaining = total - done;
  if (remaining <= 0) return 0;
  const rate = done / elapsedSec; // stocks/sec
  if (rate <= 0) return null;
  return remaining / rate;
}

export function ScanStatusCard({ status, isFetching }: Props) {
  const stopMutation = useStopScan();
  const elapsedSec = useElapsedSeconds(status);

  if (!status) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">
          Caricamento stato scan…
        </CardContent>
      </Card>
    );
  }

  // Empty state: never run
  if (!status.last_run_id) {
    return (
      <Card>
        <CardContent className="p-4 flex items-center gap-3 text-sm text-muted-foreground">
          <PlayCircle className="h-5 w-5" />
          <span>
            Nessuno scan ancora eseguito. Clicca <strong>Esegui scan ora</strong> per
            generare il primo set di segnali.
          </span>
        </CardContent>
      </Card>
    );
  }

  const isRunning = status.is_running;
  const isStale = status.is_stale;
  const pct =
    status.progress_total > 0
      ? Math.round((status.progress_done / status.progress_total) * 100)
      : 0;

  const etaSec = isRunning
    ? computeEtaSec(elapsedSec, status.progress_done, status.progress_total)
    : null;

  // Status icon: stale gets the warning treatment to make it visually obvious
  // the scan needs intervention (vs the regular spinner for healthy progress).
  const statusIcon = isStale ? (
    <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
  ) : isRunning ? (
    <Loader2 className="h-5 w-5 animate-spin text-primary" />
  ) : status.status === "success" ? (
    <CheckCircle2 className="h-5 w-5 text-green-600" />
  ) : status.status === "failed" ? (
    <AlertCircle className="h-5 w-5 text-destructive" />
  ) : (
    <Clock className="h-5 w-5 text-muted-foreground" />
  );

  const triggerLabel =
    status.trigger === "cron" ? "automatico (cron)" : "manuale";

  const phaseLabel =
    status.phase === "fetching"
      ? "Scaricamento dati di mercato (yfinance)"
      : status.phase === "evaluating"
        ? "Valutazione regole sugli stock"
        : null;

  // Card border/bg signals state at a glance:
  //   stuck → amber (attention needed)
  //   running healthy → primary tint
  //   else → default
  const cardClass = isStale
    ? "border-amber-400/70 bg-amber-50/60 dark:bg-amber-950/20"
    : isRunning
      ? "border-primary/50 bg-primary/5"
      : undefined;

  return (
    <Card className={cn(cardClass)}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start gap-3">
          {statusIcon}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <strong className="text-sm">
                {isStale && "Scan bloccato"}
                {!isStale && isRunning && "Scan in corso"}
                {!isRunning && status.status === "success" && "Ultimo scan completato"}
                {!isRunning && status.status === "failed" && "Ultimo scan fallito"}
              </strong>
              <span className="text-xs text-muted-foreground">— {triggerLabel}</span>
              {isFetching && !isRunning && (
                <span className="text-xs text-muted-foreground">(refreshing…)</span>
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
              <span>Avviato: {formatDate(status.started_at)}</span>
              <span aria-hidden>·</span>
              <span>
                Durata:{" "}
                <span className="tabular-nums">{formatSecs(elapsedSec)}</span>
                {isStale && (
                  <span className="ml-1 text-amber-700 dark:text-amber-300 italic">
                    (bloccato — counter fermo all'ultimo heartbeat)
                  </span>
                )}
              </span>
              {isRunning && etaSec != null && !isStale && (
                <>
                  <span aria-hidden>·</span>
                  <span title="Stima basata sulla velocità media finora">
                    ETA: <span className="tabular-nums font-medium">~{formatSecs(etaSec)}</span>
                  </span>
                </>
              )}
            </div>
            {isRunning && phaseLabel && !isStale && (
              <div className="text-xs text-primary font-medium mt-1">
                Fase: {phaseLabel}
              </div>
            )}
          </div>

          {/* Stop button — visible only while running. Always enabled (covers
              both live cancel + force-close-orphan cases server-side). */}
          {isRunning && (
            <Button
              variant={isStale ? "default" : "outline"}
              size="sm"
              className={cn(
                "shrink-0",
                isStale && "bg-amber-600 hover:bg-amber-700 text-white border-amber-600",
              )}
              disabled={stopMutation.isPending}
              onClick={() => stopMutation.mutate()}
              title={
                isStale
                  ? "Force-close del row 'running' bloccato (cleanup)"
                  : "Ferma lo scan in corso (entro pochi secondi)"
              }
            >
              <StopCircle className="h-4 w-4 mr-1" />
              {isStale ? "Termina (forzato)" : "Stop"}
            </Button>
          )}
        </div>

        {/* Stale warning banner — explains *why* the row is stuck and what
            the Stop button will do. Without this the user might assume the
            scan is just slow. */}
        {isStale && status.seconds_since_last_progress != null && (
          <div className="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100 rounded px-2 py-1.5 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>
              Nessun heartbeat dal worker da{" "}
              <strong className="tabular-nums">
                {formatSecs(status.seconds_since_last_progress)}
              </strong>
              . Il processo backend potrebbe essere crashato. Premi{" "}
              <strong>Termina (forzato)</strong> per chiudere la row e poter
              avviare un nuovo scan.
            </span>
          </div>
        )}

        {/* Progress bar — visible only while running. The percentage chip
            is overlayed on the bar itself for tighter visual coupling
            between the value and the bar. */}
        {isRunning && status.progress_total > 0 && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">
                {status.progress_done} / {status.progress_total} stock{" "}
                {status.phase === "fetching" ? "scaricati" : "valutati"}
              </span>
              <span className="font-semibold tabular-nums">{pct}%</span>
            </div>
            <div className="relative h-3 rounded-full bg-muted overflow-hidden">
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

        {/* Counters — always visible if we have data */}
        {(status.stocks_scanned !== null || status.alerts_fired !== null) && (
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="p-2 rounded bg-muted/50">
              <div className="text-muted-foreground">Scansionati</div>
              <div className="font-semibold tabular-nums">
                {status.stocks_scanned ?? 0}
              </div>
            </div>
            <div className="p-2 rounded bg-muted/50">
              <div className="text-muted-foreground">Saltati</div>
              <div className="font-semibold tabular-nums">
                {status.stocks_skipped ?? 0}
              </div>
            </div>
            <div
              className={cn(
                "p-2 rounded",
                (status.alerts_fired ?? 0) > 0
                  ? "bg-green-100 dark:bg-green-900/30"
                  : "bg-muted/50",
              )}
            >
              <div className="text-muted-foreground">Segnali generati</div>
              <div className="font-semibold tabular-nums">
                {status.alerts_fired ?? 0}
              </div>
            </div>
          </div>
        )}

        {status.error_message && (
          <div className="text-xs text-destructive bg-destructive/10 rounded p-2">
            {status.error_message}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
