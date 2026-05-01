import { AlertCircle, CheckCircle2, Clock, Loader2, PlayCircle } from "lucide-react";

import type { ScanStatusInfo } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
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

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const startMs = new Date(start).getTime();
  const endMs = end ? new Date(end).getTime() : Date.now();
  const sec = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}m ${rem}s`;
}

export function ScanStatusCard({ status, isFetching }: Props) {
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
            generare il primo set di alert.
          </span>
        </CardContent>
      </Card>
    );
  }

  const isRunning = status.is_running;
  const pct =
    status.progress_total > 0
      ? Math.round((status.progress_done / status.progress_total) * 100)
      : 0;

  const statusIcon = isRunning ? (
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

  return (
    <Card className={cn(isRunning && "border-primary/50 bg-primary/5")}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start gap-3">
          {statusIcon}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <strong className="text-sm">
                {isRunning && "Scan in corso"}
                {!isRunning && status.status === "success" && "Ultimo scan completato"}
                {!isRunning && status.status === "failed" && "Ultimo scan fallito"}
              </strong>
              <span className="text-xs text-muted-foreground">— {triggerLabel}</span>
              {isFetching && !isRunning && (
                <span className="text-xs text-muted-foreground">(refreshing…)</span>
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Avviato: {formatDate(status.started_at)} · Durata:{" "}
              {formatDuration(status.started_at, status.completed_at)}
            </div>
            {isRunning && phaseLabel && (
              <div className="text-xs text-primary font-medium mt-1">
                Fase: {phaseLabel}
              </div>
            )}
          </div>
        </div>

        {/* Progress bar — visible only while running */}
        {isRunning && status.progress_total > 0 && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">
                {status.progress_done} / {status.progress_total} stock{" "}
                {status.phase === "fetching" ? "scaricati" : "valutati"}
              </span>
              <span className="font-medium tabular-nums">{pct}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-500"
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
              <div className="text-muted-foreground">Alert generati</div>
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
