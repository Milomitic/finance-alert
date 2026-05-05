import { Bell } from "lucide-react";

import type { Alert, TopStock } from "@/api/types";
import { AlertsByIndexBars } from "@/components/dashboard/AlertsByIndexBars";
import { RecentAlertsFeed } from "@/components/dashboard/RecentAlertsFeed";
import { TopStocksTable } from "@/components/dashboard/TopStocksTable";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Props {
  topStocks: TopStock[];
  recentAlerts: Alert[];
  alertsLast24h: number;
  alertsPrev24h: number;
}

export function AlertsCompactPanel({ topStocks, recentAlerts, alertsLast24h, alertsPrev24h }: Props) {
  const delta = alertsLast24h - alertsPrev24h;
  const deltaLabel = delta === 0 ? "= ieri" : `${delta > 0 ? "+" : ""}${delta} vs ieri`;
  return (
    <Card>
      <CardContent className="p-0">
        <Tabs defaultValue="top">
          <div className="flex items-center border-b px-3 bg-muted/30 py-2 gap-3">
            <SectionTitle icon={Bell} label="Alerts" />
            <span className="text-sm bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200 px-2.5 py-0.5 rounded-full font-semibold">
              {alertsLast24h} ult. 24h · {deltaLabel}
            </span>
            <TabsList className="h-9 bg-transparent rounded-none">
              <TabsTrigger value="top" className="text-sm h-8 px-3">Top stocks</TabsTrigger>
              <TabsTrigger value="feed" className="text-sm h-8 px-3">Feed</TabsTrigger>
              <TabsTrigger value="byindex" className="text-sm h-8 px-3">Per indice</TabsTrigger>
            </TabsList>
            <a href="/alerts" className="ml-auto text-sm text-blue-600 dark:text-blue-400 hover:underline pr-2">Vedi tutti →</a>
          </div>
          <TabsContent value="top" className="m-0">
            <TopStocksTable data={topStocks} />
          </TabsContent>
          <TabsContent value="feed" className="m-0">
            <RecentAlertsFeed alerts={recentAlerts} />
          </TabsContent>
          <TabsContent value="byindex" className="m-0">
            <AlertsByIndexBars />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
