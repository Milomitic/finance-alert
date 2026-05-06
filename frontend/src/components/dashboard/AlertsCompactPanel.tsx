import { Bell } from "lucide-react";

import type { Alert, AlertsByIndexPoint, TopStock } from "@/api/types";
import { AlertsByIndexBars } from "@/components/dashboard/AlertsByIndexBars";
import { RecentAlertsFeed } from "@/components/dashboard/RecentAlertsFeed";
import { TopStocksTable } from "@/components/dashboard/TopStocksTable";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";

interface Props {
  topStocks: TopStock[];
  recentAlerts: Alert[];
  alertsByIndex: AlertsByIndexPoint[];
  alertsLast24h: number;
  alertsPrev24h: number;
}

const COLUMNS: { key: string; label: string }[] = [
  { key: "top", label: "Top stocks" },
  { key: "feed", label: "Feed" },
  { key: "byindex", label: "Per indice" },
];

/**
 * Was: a 3-tab card (Top stocks / Feed / Per indice). The user
 * preferred to see all three at once, so the tabs collapsed into
 * three side-by-side columns. The "Per indice" column shipped in
 * Fase 3E and now displays the real per-index alert breakdown
 * (count of alerts in the last 30 days per index, descending).
 */
export function AlertsCompactPanel({
  topStocks,
  recentAlerts,
  alertsByIndex,
  alertsLast24h,
  alertsPrev24h,
}: Props) {
  const delta = alertsLast24h - alertsPrev24h;
  const deltaLabel =
    delta === 0 ? "= ieri" : `${delta > 0 ? "+" : ""}${delta} vs ieri`;

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        {/* Header — title + 24h badge + "Vedi tutti" link. */}
        <div className="shrink-0 flex items-center gap-3 border-b px-3 bg-muted/30 py-2">
          <SectionTitle
            icon={Bell}
            label="Alerts"
            right={
              <span className="text-[11px] bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200 px-2 py-0.5 rounded-full font-semibold whitespace-nowrap">
                {alertsLast24h} ult. 24h · {deltaLabel}
              </span>
            }
          />
          <a
            href="/alerts"
            className="ml-auto text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
          >
            Vedi tutti →
          </a>
        </div>

        {/* Three-column grid — one per former tab. Each column is a
            flex-col with a fixed header and a scrollable body so the
            card height stays predictable (matches Top Picks beside it)
            even when Feed has many items. */}
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border/40">
          {COLUMNS.map((col) => (
            <div key={col.key} className="flex flex-col min-h-0 min-w-0">
              <div className="shrink-0 px-3 py-1.5 text-[11.5px] uppercase tracking-[0.16em] font-bold text-muted-foreground border-b bg-muted/40">
                {col.label}
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto">
                {col.key === "top" && <TopStocksTable data={topStocks} />}
                {col.key === "feed" && <RecentAlertsFeed alerts={recentAlerts} />}
                {col.key === "byindex" && <AlertsByIndexBars data={alertsByIndex} />}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
