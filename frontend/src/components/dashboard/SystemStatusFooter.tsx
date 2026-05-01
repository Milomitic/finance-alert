import { Server, ServerOff, MessageSquare, MessageSquareOff } from "lucide-react";

import type { SystemStatus } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";

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

export function SystemStatusFooter({ status }: Props) {
  return (
    <Card>
      <CardContent className="px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm text-muted-foreground">
        <span className="flex items-center gap-1.5">
          {status.scheduler_running ? (
            <><Server className="h-4 w-4 text-green-600" />Scheduler attivo</>
          ) : (
            <><ServerOff className="h-4 w-4 text-destructive" />Scheduler offline</>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          {status.telegram_configured ? (
            <><MessageSquare className="h-4 w-4 text-green-600" />Telegram OK</>
          ) : (
            <><MessageSquareOff className="h-4 w-4 text-amber-600" />Telegram non configurato</>
          )}
        </span>
        <span>Prossimo scan: <strong className="text-foreground tabular-nums">{fmtShort(status.scan_alerts_next_run)}</strong></span>
        <span>Prossimo digest: <strong className="text-foreground tabular-nums">{fmtShort(status.send_digest_next_run)}</strong></span>
        {status.last_digest_sent_at && (
          <span>Ultimo digest: <strong className="text-foreground tabular-nums">{fmtShort(status.last_digest_sent_at)}</strong></span>
        )}
        <span className="ml-auto text-muted-foreground/70">⟳ aggiornamento ogni 30s</span>
      </CardContent>
    </Card>
  );
}
