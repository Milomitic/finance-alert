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
          <div className="flex items-center border-b px-2 bg-muted/30">
            <span className="text-[11px] font-semibold py-1.5 pl-1 pr-2">Alerts</span>
            <span className="text-[10px] bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200 px-2 py-0.5 rounded-full font-semibold">
              {alertsLast24h} ult. 24h · {deltaLabel}
            </span>
            <TabsList className="h-8 ml-3 bg-transparent rounded-none">
              <TabsTrigger value="trend" className="text-[10px] h-7 px-2">Trend 30gg</TabsTrigger>
              <TabsTrigger value="top" className="text-[10px] h-7 px-2">Top stocks</TabsTrigger>
              <TabsTrigger value="feed" className="text-[10px] h-7 px-2">Feed</TabsTrigger>
              <TabsTrigger value="byindex" className="text-[10px] h-7 px-2">Per indice</TabsTrigger>
            </TabsList>
            <a href="/alerts" className="ml-auto text-[10px] text-blue-600 dark:text-blue-400 hover:underline pr-2">Vedi tutti →</a>
          </div>
          <TabsContent value="trend" className="m-0">
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
