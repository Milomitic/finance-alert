import type { Alert, AlertsByDayPoint, TopStock } from "@/api/types";
import { AlertsByDayChart } from "@/components/dashboard/AlertsByDayChart";
import { AlertsByIndexBars } from "@/components/dashboard/AlertsByIndexBars";
import { RecentAlertsFeed } from "@/components/dashboard/RecentAlertsFeed";
import { TopStocksTable } from "@/components/dashboard/TopStocksTable";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Props {
  alertsByDay: AlertsByDayPoint[];
  topStocks: TopStock[];
  recentAlerts: Alert[];
  alertsLast24h: number;
  alertsPrev24h: number;
}

export function AlertsCompactPanel({ alertsByDay, topStocks, recentAlerts, alertsLast24h, alertsPrev24h }: Props) {
  const delta = alertsLast24h - alertsPrev24h;
  const deltaLabel = delta === 0 ? "= ieri" : `${delta > 0 ? "+" : ""}${delta} vs ieri`;
  return (
    <Card>
      <CardContent className="p-0">
        <Tabs defaultValue="trend">
          <div className="flex items-center border-b px-3 bg-muted/30">
            <span className="text-sm font-semibold uppercase tracking-wide py-2 pl-1 pr-3">Alerts</span>
            <span className="text-sm bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200 px-2.5 py-0.5 rounded-full font-semibold">
              {alertsLast24h} ult. 24h · {deltaLabel}
            </span>
            <TabsList className="h-10 ml-4 bg-transparent rounded-none">
              <TabsTrigger value="trend" className="text-sm h-9 px-3">Trend 30gg</TabsTrigger>
              <TabsTrigger value="top" className="text-sm h-9 px-3">Top stocks</TabsTrigger>
              <TabsTrigger value="feed" className="text-sm h-9 px-3">Feed</TabsTrigger>
              <TabsTrigger value="byindex" className="text-sm h-9 px-3">Per indice</TabsTrigger>
            </TabsList>
            <a href="/alerts" className="ml-auto text-sm text-blue-600 dark:text-blue-400 hover:underline pr-2">Vedi tutti →</a>
          </div>
          <TabsContent value="trend" className="m-0 px-3 py-2">
            <AlertsByDayChart data={alertsByDay} compact />
          </TabsContent>
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
