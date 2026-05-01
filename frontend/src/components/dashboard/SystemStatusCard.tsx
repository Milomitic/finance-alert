import { CheckCircle2, MessageSquare, MessageSquareOff, Server, ServerOff } from "lucide-react";

import type { SystemStatus } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  status: SystemStatus;
}

function formatNext(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("it-IT", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export function SystemStatusCard({ status }: Props) {
  return (
    <Card>
      <CardContent className="p-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
        <span className="flex items-center gap-1.5">
          {status.scheduler_running ? (
            <>
              <Server className="h-4 w-4 text-green-600" />
              <span>Scheduler attivo</span>
            </>
          ) : (
            <>
              <ServerOff className="h-4 w-4 text-destructive" />
              <span>Scheduler offline</span>
            </>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          {status.telegram_configured ? (
            <>
              <MessageSquare className="h-4 w-4 text-green-600" />
              <span>Telegram configurato</span>
            </>
          ) : (
            <>
              <MessageSquareOff className="h-4 w-4 text-amber-600" />
              <span>Telegram non configurato</span>
            </>
          )}
        </span>
        <span className="text-muted-foreground">
          Prossimo scan: <strong>{formatNext(status.scan_alerts_next_run)}</strong>
        </span>
        <span className="text-muted-foreground">
          Prossimo digest: <strong>{formatNext(status.send_digest_next_run)}</strong>
        </span>
        {status.last_digest_sent_at && (
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Ultimo digest: {formatNext(status.last_digest_sent_at)}
          </span>
        )}
      </CardContent>
    </Card>
  );
}
