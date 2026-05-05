import { Bell } from "lucide-react";
import { useState } from "react";

import type { Alert, TopStock } from "@/api/types";
import { AlertsByIndexBars } from "@/components/dashboard/AlertsByIndexBars";
import { RecentAlertsFeed } from "@/components/dashboard/RecentAlertsFeed";
import { TopStocksTable } from "@/components/dashboard/TopStocksTable";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

interface Props {
  topStocks: TopStock[];
  recentAlerts: Alert[];
  alertsLast24h: number;
  alertsPrev24h: number;
}

type TabKey = "top" | "feed" | "byindex";

const TABS: { key: TabKey; label: string }[] = [
  { key: "top", label: "Top stocks" },
  { key: "feed", label: "Feed" },
  { key: "byindex", label: "Per indice" },
];

export function AlertsCompactPanel({
  topStocks,
  recentAlerts,
  alertsLast24h,
  alertsPrev24h,
}: Props) {
  const [tab, setTab] = useState<TabKey>("top");
  const delta = alertsLast24h - alertsPrev24h;
  const deltaLabel =
    delta === 0 ? "= ieri" : `${delta > 0 ? "+" : ""}${delta} vs ieri`;

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        {/* Header — title + 24h badge + "Vedi tutti" link.
            Was a single row with the tabs inline; tabs moved to their own
            row below to match the TopMovers / TopPicks layout. */}
        <div className="flex items-center gap-3 border-b px-3 bg-muted/30 py-2">
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

        {/* Canonical button-strip tabs — same pattern as TopMovers / TopPicks /
            (the just-refactored) FiftyTwoWeekVolCard. */}
        <div className="flex shrink-0 border-b">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                "flex-1 text-[11px] font-bold uppercase tracking-wider py-1.5 transition-colors border-r last:border-r-0",
                tab === t.key
                  ? "bg-background shadow-inner text-foreground"
                  : "text-muted-foreground hover:bg-muted/30",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        {tab === "top" && <TopStocksTable data={topStocks} />}
        {tab === "feed" && <RecentAlertsFeed alerts={recentAlerts} />}
        {tab === "byindex" && <AlertsByIndexBars />}
      </CardContent>
    </Card>
  );
}
