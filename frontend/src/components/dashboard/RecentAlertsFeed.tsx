import { useState } from "react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { TONE_BG, getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
}

export function RecentAlertsFeed({ alerts }: Props) {
  const [openDetail, setOpenDetail] = useState<Alert | null>(null);

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Alert recenti</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {alerts.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              Nessun alert recente. Esegui uno scan da{" "}
              <span className="underline">/alerts</span> per generarli.
            </div>
          ) : (
            <ul className="divide-y">
              {alerts.map((a) => {
                const meta = getAlertKindMeta(a.rule_kind);
                const Icon = meta.icon;
                return (
                  <li
                    key={a.id}
                    className="px-4 py-3 cursor-pointer hover:bg-accent transition-colors flex items-center gap-3"
                    onClick={() => setOpenDetail(a)}
                  >
                    {/* Tone-colored kind chip with icon — replaces the
                        previous emoji-only marker; consistent with the rest
                        of the alert UI surfaces (table, history card, dialog) */}
                    <span
                      className={cn(
                        "inline-flex items-center justify-center h-6 w-6 rounded shrink-0",
                        TONE_BG[meta.tone],
                      )}
                      title={meta.label}
                    >
                      <Icon className="h-3.5 w-3.5" />
                    </span>
                    {a.ticker ? (
                      <Link
                        to={`/stocks/${encodeURIComponent(a.ticker)}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium min-w-[60px] hover:underline"
                      >
                        {a.ticker}
                      </Link>
                    ) : (
                      <span className="font-medium min-w-[60px]">—</span>
                    )}
                    <span
                      className="text-xs text-muted-foreground truncate max-w-[160px]"
                      title={a.name ?? ""}
                    >
                      {a.name ?? ""}
                    </span>
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded text-xs font-semibold",
                        TONE_BG[meta.tone],
                      )}
                    >
                      {meta.label}
                    </span>
                    <span className="text-sm tabular-nums">${a.trigger_price}</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {new Date(a.triggered_at).toLocaleString("it-IT", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={openDetail} onClose={() => setOpenDetail(null)} />
    </>
  );
}
