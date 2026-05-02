import { AlertCircle, RefreshCw } from "lucide-react";

import { AlertsCompactPanel } from "@/components/dashboard/AlertsCompactPanel";
import { BreadthMatrixTable } from "@/components/dashboard/BreadthMatrixTable";
import { FiftyTwoWeekVolCard } from "@/components/dashboard/FiftyTwoWeekVolCard";
import { HeroStrip } from "@/components/dashboard/HeroStrip";
import { MarketTreemap } from "@/components/dashboard/MarketTreemap";
import { MoversCard } from "@/components/dashboard/MoversCard";
import { RsiHistogramCard } from "@/components/dashboard/RsiHistogramCard";
import { SectorsHeatmapCard } from "@/components/dashboard/SectorsHeatmapCard";
import { SpotlightCards } from "@/components/dashboard/SpotlightCards";
import { SystemStatusFooter } from "@/components/dashboard/SystemStatusFooter";
import { Card, CardContent } from "@/components/ui/card";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import { useMarketSummary } from "@/hooks/useMarketSummary";

function MarketUnavailable() {
  return (
    <Card>
      <CardContent className="p-6 text-center">
        <AlertCircle className="h-5 w-5 text-muted-foreground mx-auto mb-2" />
        <div className="text-sm font-semibold">Nessuno scan ancora eseguito</div>
        <div className="text-xs text-muted-foreground mt-1">
          Vai su <a href="/alerts" className="text-blue-600 hover:underline">/alerts</a> e clicca <strong>Esegui scan ora</strong> per generare il primo snapshot di mercato.
        </div>
      </CardContent>
    </Card>
  );
}

function MarketError({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-3 text-sm">
        <AlertCircle className="h-5 w-5 text-destructive" />
        <span>Errore nel caricamento del riepilogo di mercato.</span>
        <button onClick={onRetry} className="ml-auto text-blue-600 hover:underline flex items-center gap-1">
          <RefreshCw className="h-3 w-3" /> Riprova
        </button>
      </CardContent>
    </Card>
  );
}

export default function HomePage() {
  const market = useMarketSummary();
  const summary = useDashboardSummary();

  // Loading skeleton
  if (market.isLoading || summary.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid lg:grid-cols-[340px_1fr_200px] gap-3">
          <Card><CardContent className="p-4 h-[80px] animate-pulse bg-muted/40" /></Card>
          <Card><CardContent className="p-4 h-[80px] animate-pulse bg-muted/40" /></Card>
          <Card><CardContent className="p-4 h-[80px] animate-pulse bg-muted/40" /></Card>
        </div>
        <Card><CardContent className="p-0 h-[200px] animate-pulse bg-muted/40" /></Card>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i}><CardContent className="p-4 h-[160px] animate-pulse bg-muted/40" /></Card>
          ))}
        </div>
      </div>
    );
  }

  const summaryData = summary.data;

  // Market unavailable (no snapshot yet) — still show alerts panel below if summary loaded
  if (market.isError) {
    return (
      <div className="space-y-4">
        <MarketError onRetry={() => market.refetch()} />
        {summaryData && (
          <AlertsCompactPanel
            alertsByDay={summaryData.alerts_by_day}
            topStocks={summaryData.top_stocks_30d}
            recentAlerts={summaryData.recent_alerts}
            alertsLast24h={summaryData.kpis.alerts_last_24h}
            alertsPrev24h={summaryData.kpis.alerts_prev_24h}
          />
        )}
      </div>
    );
  }

  if (!market.data || market.data.available === false) {
    return (
      <div className="space-y-4">
        <MarketUnavailable />
        {summaryData && (
          <AlertsCompactPanel
            alertsByDay={summaryData.alerts_by_day}
            topStocks={summaryData.top_stocks_30d}
            recentAlerts={summaryData.recent_alerts}
            alertsLast24h={summaryData.kpis.alerts_last_24h}
            alertsPrev24h={summaryData.kpis.alerts_prev_24h}
          />
        )}
        {summaryData && <SystemStatusFooter status={summaryData.system_status} />}
      </div>
    );
  }

  // Happy path — destructure with defaults to satisfy TS (all fields are optional in API type)
  const m = market.data;
  if (!m.global || !m.by_index || !m.movers || !m.rsi_distribution || !m.sectors || !m.treemap) {
    return <MarketError onRetry={() => market.refetch()} />;
  }
  const nextScanAt = summaryData?.kpis.next_scan_at ?? null;

  return (
    <div className="space-y-4">
      <HeroStrip
        global={m.global}
        byIndex={m.by_index}
        computedAt={m.computed_at}
        isStale={m.is_stale}
        nextScanAt={nextScanAt}
      />
      <BreadthMatrixTable data={m.by_index} />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <MoversCard movers={m.movers} />
        <RsiHistogramCard rsi={m.rsi_distribution} indices={m.by_index} />
        <SectorsHeatmapCard sectors={m.sectors} />
        <FiftyTwoWeekVolCard movers={m.movers} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2">
          <MarketTreemap treemap={m.treemap} indices={m.by_index} />
        </div>
        <SpotlightCards />
      </div>
      {summaryData && (
        <AlertsCompactPanel
          alertsByDay={summaryData.alerts_by_day}
          topStocks={summaryData.top_stocks_30d}
          recentAlerts={summaryData.recent_alerts}
          alertsLast24h={summaryData.kpis.alerts_last_24h}
          alertsPrev24h={summaryData.kpis.alerts_prev_24h}
        />
      )}
      {summaryData && <SystemStatusFooter status={summaryData.system_status} />}
    </div>
  );
}
