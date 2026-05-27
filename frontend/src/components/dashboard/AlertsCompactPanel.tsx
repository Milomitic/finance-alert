import { Bell } from "lucide-react";

import type { Alert, AlertsByIndexPoint, TopStock } from "@/api/types";
import { AlertsByIndexBars } from "@/components/dashboard/AlertsByIndexBars";
import { ConfluenceRows } from "@/components/dashboard/ConfluenceCard";
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
  { key: "confluence", label: "Top confluenze" },
  { key: "top", label: "Top stocks" },
  { key: "feed", label: "Feed" },
  { key: "byindex", label: "Per indice" },
];

/**
 * Was: a 3-tab card (Top stocks / Feed / Per indice), then 3 side-by-side
 * columns. 2026-05: absorbed the former standalone "Top confluenze" card as
 * a FOURTH column on the left (4 equal columns → the original three each
 * shrink proportionally to ~75% width). Each column is a flex-col with a
 * fixed header and a scrollable body so the card height stays predictable.
 */
export function AlertsCompactPanel({
  topStocks,
  recentAlerts,
  alertsByIndex,
  alertsLast24h,
}: Props) {
  return (
    <Card className="md:h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        {/* Header — title + 24h badge + "Vedi tutti" link. */}
        <div className="shrink-0 flex items-center gap-3 border-b px-3 bg-muted/30 py-2">
          <SectionTitle
            icon={Bell}
            label="Segnali"
            right={
              <span
                className="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200 px-2 py-0.5 rounded-full font-semibold whitespace-nowrap"
                title="Nuovi segnali rilevati nelle ultime 24 ore"
              >
                {alertsLast24h} nuovi segnali · 24h
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
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-border/40">
          {COLUMNS.map((col) => (
            <div key={col.key} className="flex flex-col min-h-0 min-w-0">
              <div className="shrink-0 px-3 py-1.5 text-xs uppercase tracking-[0.16em] font-bold text-muted-foreground border-b bg-muted/40">
                {col.label}
              </div>
              {/* Mobile: natural flow capped at 55vh so a long Feed
                  doesn't run away — the page scrolls. md+: fixed-height
                  pane with its own scroll (keeps the 4 columns aligned
                  to the card height). */}
              <div className="max-h-[55vh] overflow-y-auto md:max-h-none md:flex-1 md:min-h-0">
                {col.key === "confluence" && <ConfluenceRows />}
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
