import { AlertCircle, Bell, FileBarChart2, ListChecks, ScanSearch } from "lucide-react";

import { AlertsByDayChart } from "@/components/dashboard/AlertsByDayChart";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { RecentAlertsFeed } from "@/components/dashboard/RecentAlertsFeed";
import { SystemStatusCard } from "@/components/dashboard/SystemStatusCard";
import { TopStocksTable } from "@/components/dashboard/TopStocksTable";
import { Card, CardContent } from "@/components/ui/card";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";

function deltaLabel(curr: number, prev: number): string {
  const diff = curr - prev;
  if (diff === 0) return "= ieri";
  const arrow = diff > 0 ? "↑" : "↓";
  const sign = diff > 0 ? "+" : "";
  return `${sign}${diff} vs ieri ${arrow}`;
}

function lastScanLabel(
  lastScan: ReturnType<typeof useDashboardSummary>["data"] extends infer T
    ? T extends { kpis: { last_scan: infer S } }
      ? S
      : never
    : never,
): string {
  if (!lastScan) return "Mai eseguito";
  if (lastScan.is_running) return "In corso…";
  if (lastScan.completed_at) {
    const dt = new Date(lastScan.completed_at);
    return dt.toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
  }
  return "—";
}

export default function HomePage() {
  const q = useDashboardSummary();

  if (q.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4 h-[88px] animate-pulse bg-muted/40" />
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="h-[260px] animate-pulse bg-muted/40" />
        </Card>
      </div>
    );
  }

  if (q.isError || !q.data) {
    return (
      <Card>
        <CardContent className="p-6 flex items-center gap-3 text-sm">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <span>Errore nel caricamento del riepilogo dashboard.</span>
          <button
            className="underline"
            onClick={() => q.refetch()}
          >
            Riprova
          </button>
        </CardContent>
      </Card>
    );
  }

  const { kpis, alerts_by_day, top_stocks_30d, recent_alerts, system_status } = q.data;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Dashboard</h2>
        <p className="text-sm text-muted-foreground">
          Riepilogo dell'attività di monitoring (aggiornato ogni 30s)
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          title="Alert ultime 24h"
          value={kpis.alerts_last_24h}
          subtext={deltaLabel(kpis.alerts_last_24h, kpis.alerts_prev_24h)}
          icon={<Bell className="h-4 w-4" />}
        />
        <KpiCard
          title="Non letti"
          value={kpis.alerts_unread}
          subtext={
            kpis.alerts_unread > 0
              ? "vedi /alerts per gestirli"
              : "tutti gestiti"
          }
          icon={<FileBarChart2 className="h-4 w-4" />}
          tone={kpis.alerts_unread > 0 ? "warning" : "default"}
        />
        <KpiCard
          title="Stock monitorati"
          value={kpis.stocks_monitored}
          subtext={`${kpis.indices_count} indici`}
          icon={<ListChecks className="h-4 w-4" />}
        />
        <KpiCard
          title="Ultimo scan"
          value={lastScanLabel(kpis.last_scan)}
          subtext={
            kpis.last_scan?.alerts_fired != null
              ? `${kpis.last_scan.alerts_fired} alert generati`
              : kpis.next_scan_at
                ? `Prossimo: ${new Date(kpis.next_scan_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}`
                : undefined
          }
          icon={<ScanSearch className="h-4 w-4" />}
          tone={kpis.last_scan?.status === "failed" ? "destructive" : "default"}
        />
      </div>

      {/* Chart + Top */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AlertsByDayChart data={alerts_by_day} />
        <TopStocksTable data={top_stocks_30d} />
      </div>

      {/* Recent alerts */}
      <RecentAlertsFeed alerts={recent_alerts} />

      {/* System status footer */}
      <SystemStatusCard status={system_status} />
    </div>
  );
}
