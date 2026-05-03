import { useState } from "react";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  alerts: Alert[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

export function StockAlertsHistoryCard({ alerts }: Props) {
  const [open, setOpen] = useState<Alert | null>(null);

  return (
    <>
      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Alert storici ({alerts.length})
          </div>
          {alerts.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-4">
              Nessun alert per questo ticker.
            </div>
          ) : (
            <ul className="divide-y">
              {alerts.slice(0, 10).map((a) => (
                <li
                  key={a.id}
                  className="py-1.5 cursor-pointer hover:bg-accent transition-colors text-sm flex items-center gap-2"
                  onClick={() => setOpen(a)}
                >
                  <span className="font-medium">
                    {a.rule_kind ? KIND_LABEL[a.rule_kind] ?? a.rule_kind : "Price alert"}
                  </span>
                  <span className="ml-auto text-muted-foreground tabular-nums">
                    {new Date(a.triggered_at).toLocaleString("it-IT", {
                      day: "2-digit", month: "2-digit", year: "2-digit",
                    })}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {alerts.length > 10 && (
            <div className="text-sm text-muted-foreground mt-2 text-center">
              +{alerts.length - 10} non mostrati
            </div>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={open} onClose={() => setOpen(null)} />
    </>
  );
}
