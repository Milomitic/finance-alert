import { useState } from "react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Props {
  alerts: Alert[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

const KIND_EMOJI: Record<string, string> = {
  rsi_oversold: "🟢",
  rsi_overbought: "🔴",
  golden_cross: "⚡",
  death_cross: "⚠️",
};

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
              {alerts.map((a) => (
                <li
                  key={a.id}
                  className="px-4 py-3 cursor-pointer hover:bg-accent transition-colors flex items-center gap-3"
                  onClick={() => setOpenDetail(a)}
                >
                  <span className="text-lg" aria-hidden="true">
                    {KIND_EMOJI[a.rule_kind ?? ""] ?? "•"}
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
                  <Badge variant="secondary" className="text-xs">
                    {KIND_LABEL[a.rule_kind ?? ""] ?? a.rule_kind ?? "—"}
                  </Badge>
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
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={openDetail} onClose={() => setOpenDetail(null)} />
    </>
  );
}
