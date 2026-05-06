import { Clock } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { isDelayedDetection } from "@/lib/alertDates";
import { TONE_BG, getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
}

/**
 * Was: wrapped in a Card with an "Alert recenti" CardHeader. The
 * surrounding AlertsCompactPanel column already has its own "FEED"
 * header so the inner Card produced a redundant double-frame and a
 * duplicated subtitle. Now renders raw — caller's column header is
 * the only label.
 */
export function RecentAlertsFeed({ alerts }: Props) {
  const [openDetail, setOpenDetail] = useState<Alert | null>(null);

  return (
    <>
      <div>
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
                    className="px-3 py-2 cursor-pointer hover:bg-accent transition-colors flex items-center gap-2 min-w-0"
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
                    {/* Identity block matches Top Movers / 52w / Top Stocks /
                        Top Picks: logo + ticker bold + name muted truncated.
                        The Link wraps the identity so the row stays clickable
                        for the detail dialog while ticker click navigates to
                        the stock page. */}
                    {a.ticker ? (
                      <Link
                        to={`/stocks/${encodeURIComponent(a.ticker)}`}
                        onClick={(e) => e.stopPropagation()}
                        className="flex items-center gap-2 hover:underline min-w-0 flex-1"
                      >
                        <StockIdentity ticker={a.ticker} name={a.name} />
                      </Link>
                    ) : (
                      <span className="font-medium min-w-[60px]">—</span>
                    )}
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded text-xs font-semibold shrink-0",
                        TONE_BG[meta.tone],
                      )}
                    >
                      {meta.label}
                    </span>
                    <span className="text-sm tabular-nums shrink-0">${a.trigger_price}</span>
                    {/* Date cell: signal_date is the primary "when did the
                        market do the thing"; detection time is secondary.
                        Orange clock chip flags ≥1-day-delayed detection. */}
                    {(() => {
                      const delayed = isDelayedDetection(a.triggered_at, a.signal_date);
                      return (
                        <span
                          className="ml-auto text-xs text-muted-foreground tabular-nums inline-flex items-center gap-1"
                          title={
                            a.signal_date
                              ? `Segnale: ${a.signal_date} · Rilevato: ${new Date(a.triggered_at).toLocaleString("it-IT")}`
                              : new Date(a.triggered_at).toLocaleString("it-IT")
                          }
                        >
                          {delayed && (
                            <Clock className="h-3 w-3 text-amber-600 dark:text-amber-400" />
                          )}
                          {a.signal_date
                            ? new Date(a.signal_date).toLocaleDateString("it-IT", {
                                day: "2-digit",
                                month: "2-digit",
                              })
                            : new Date(a.triggered_at).toLocaleString("it-IT", {
                                day: "2-digit",
                                month: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                        </span>
                      );
                    })()}
                  </li>
                );
              })}
            </ul>
          )}
      </div>
      <AlertDetailDialog alert={openDetail} onClose={() => setOpenDetail(null)} />
    </>
  );
}
