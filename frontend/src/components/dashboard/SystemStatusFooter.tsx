import {
  Activity, Calendar, CheckCircle2, MessageSquare, MessageSquareOff,
  RefreshCw, Server, ServerOff, Send,
} from "lucide-react";

import type { SystemStatus } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  status: SystemStatus;
}

function fmtShort(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function relTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    const t = new Date(iso).getTime();
    const now = Date.now();
    const diffMs = t - now;
    const abs = Math.abs(diffMs);
    const past = diffMs < 0;
    const min = Math.round(abs / 60_000);
    const hr = Math.round(abs / 3_600_000);
    const day = Math.round(abs / 86_400_000);
    let unit: string;
    if (abs < 60_000) unit = "<1m";
    else if (min < 60) unit = `${min}m`;
    else if (hr < 36) unit = `${hr}h`;
    else unit = `${day}g`;
    return past ? `${unit} fa` : `tra ${unit}`;
  } catch {
    return "";
  }
}

interface CellProps {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "ok" | "warn" | "err" | "neutral";
}

function StatusCell({ icon: Icon, label, value, hint, tone = "neutral" }: CellProps) {
  const toneClass = {
    ok: "text-green-600 dark:text-green-400",
    warn: "text-amber-600 dark:text-amber-400",
    err: "text-red-600 dark:text-red-400",
    neutral: "text-muted-foreground",
  }[tone];
  return (
    <div className="flex items-start gap-2.5 min-w-0">
      <Icon className={cn("h-5 w-5 mt-0.5 shrink-0", toneClass)} />
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
          {label}
        </div>
        <div className="text-sm font-semibold tabular-nums truncate" title={typeof value === "string" ? value : undefined}>
          {value}
        </div>
        {hint && <div className="text-[11px] text-muted-foreground tabular-nums">{hint}</div>}
      </div>
    </div>
  );
}

/**
 * Structured footer showing scheduler health, next/last job times, and digest
 * status. Replaces the previous single-line "wall of text" layout with a
 * proper grid of labelled cells.
 */
export function SystemStatusFooter({ status }: Props) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-3 pb-2 border-b border-border/50">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            System status
          </span>
          <span className="ml-auto text-[11px] text-muted-foreground inline-flex items-center gap-1">
            <RefreshCw className="h-3 w-3" /> aggiornamento ogni 30s
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-6 gap-y-3">
          <StatusCell
            icon={status.scheduler_running ? Server : ServerOff}
            label="Scheduler"
            value={status.scheduler_running ? "Attivo" : "Offline"}
            tone={status.scheduler_running ? "ok" : "err"}
          />
          <StatusCell
            icon={status.telegram_configured ? MessageSquare : MessageSquareOff}
            label="Telegram"
            value={status.telegram_configured ? "Configurato" : "Non configurato"}
            tone={status.telegram_configured ? "ok" : "warn"}
          />
          <StatusCell
            icon={Calendar}
            label="Prossimo scan"
            value={fmtShort(status.scan_alerts_next_run)}
            hint={relTime(status.scan_alerts_next_run)}
          />
          <StatusCell
            icon={Send}
            label="Prossimo digest"
            value={fmtShort(status.send_digest_next_run)}
            hint={relTime(status.send_digest_next_run)}
          />
          {status.last_digest_sent_at && (
            <StatusCell
              icon={CheckCircle2}
              label="Ultimo digest"
              value={fmtShort(status.last_digest_sent_at)}
              hint={relTime(status.last_digest_sent_at)}
              tone="ok"
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
