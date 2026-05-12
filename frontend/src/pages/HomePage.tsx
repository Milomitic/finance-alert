import { AlertCircle, Clock, RefreshCw } from "lucide-react";

import { AlertsCompactPanel } from "@/components/dashboard/AlertsCompactPanel";
import { BreadthMatrixTable } from "@/components/dashboard/BreadthMatrixTable";
import { FiftyTwoWeekVolCard } from "@/components/dashboard/FiftyTwoWeekVolCard";
import { HeroStrip } from "@/components/dashboard/HeroStrip";
import { LiveVolumeMoversCard } from "@/components/dashboard/LiveVolumeMoversCard";
import { MarketTickerTape } from "@/components/dashboard/MarketTickerTape";
import { DataSourcesCard } from "@/components/dashboard/DataSourcesCard";
import { ScanHeaderButton } from "@/components/dashboard/ScanHeaderButton";
import { TopMoversCard } from "@/components/dashboard/TopMoversCard";
import { TopPicksCard } from "@/components/dashboard/TopPicksCard";
import { RsiHistogramCard } from "@/components/dashboard/RsiHistogramCard";
import { SectorsHeatmapCard } from "@/components/dashboard/SectorsHeatmapCard";
import { SuperinvestorPicksCard } from "@/components/dashboard/SuperinvestorPicksCard";
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
            topStocks={summaryData.top_stocks_30d}
            recentAlerts={summaryData.recent_alerts}
            alertsByIndex={summaryData.alerts_by_index_30d}
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
            topStocks={summaryData.top_stocks_30d}
            recentAlerts={summaryData.recent_alerts}
            alertsByIndex={summaryData.alerts_by_index_30d}
            alertsLast24h={summaryData.kpis.alerts_last_24h}
            alertsPrev24h={summaryData.kpis.alerts_prev_24h}
          />
        )}
        {summaryData && <SystemStatusFooter status={summaryData.system_status} />}
      </div>
    );
  }

  // Happy path — destructure with defaults to satisfy TS (all fields are optional in API type).
  // Note: `treemap` is no longer required (the treemap card was removed) but the API
  // continues to populate it; we just don't render it.
  const m = market.data;
  if (!m.global || !m.by_index || !m.movers || !m.rsi_distribution || !m.sectors) {
    return <MarketError onRetry={() => market.refetch()} />;
  }
  const nextScanAt = summaryData?.kpis.next_scan_at ?? null;

  return (
    <div className="space-y-4">
      {/* Ticker tape: top-of-page horizontal scroll with live indices,
          commodities, crypto. Runs always (not just during loading).
          Sets the "trading floor" tone for the page — the rest of the
          UI feels static without it. */}
      <MarketTickerTape />
      <div className="flex items-center justify-between gap-3 px-1">
        <div className="flex items-baseline gap-3">
          <h2 className="text-base font-semibold tracking-tight">Dashboard</h2>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {m.computed_at && (
              <span className={m.is_stale ? "text-amber-600 dark:text-amber-400" : ""}>
                Aggiornato {new Date(m.computed_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}
              </span>
            )}
            {nextScanAt && (
              <>
                <span className="opacity-50">·</span>
                <span className="text-blue-600 dark:text-blue-400">
                  Prossimo scan: {new Date(nextScanAt).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}
                </span>
              </>
            )}
          </div>
        </div>
        {/* Scan + digest controls — moved here from the hero strip so the
            hero is all market context. The ScanProgressToast (mounted in
            Layout) carries the in-flight progress UI. */}
        <ScanHeaderButton nextScanAt={nextScanAt} />
      </div>
      <HeroStrip global={m.global} byIndex={m.by_index} />
      {/* Row 2: same [3fr_2fr] split as HeroStrip — breadth matrix on
          the left (the wider, table-shaped artifact) + live-volume
          movers on the right (vertical list, narrower, polls live
          prices for the most actively traded stocks of the day). The
          symmetric split keeps the page rhythm consistent: row 1 and
          row 2 read as "left = aggregate state, right = live signal". */}
      <div className="grid gap-3 lg:grid-cols-[3fr_2fr]">
        <BreadthMatrixTable data={m.by_index} />
        <LiveVolumeMoversCard movers={m.movers} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 lg:h-[520px]">
        <div className="h-full min-h-0"><RsiHistogramCard rsi={m.rsi_distribution} indices={m.by_index} /></div>
        <div className="h-full min-h-0"><SectorsHeatmapCard sectors={m.sectors} /></div>
        <div className="h-full min-h-0"><TopMoversCard movers={m.movers} /></div>
        <div className="h-full min-h-0"><FiftyTwoWeekVolCard movers={m.movers} /></div>
      </div>
      {/* Alerts (left) + Top Picks (right) on the same row. The two are
          complementary: alerts is "what just happened that needs your
          attention", top picks is "what looks great right now". Putting them
          side-by-side gives the user a single decision surface — react vs
          discover — instead of scrolling between them.
          Equal-height row (`lg:h-[500px]`) so the two cards align — was
          `items-start` which let the Alerts card balloon past Top Picks
          when its Feed had a lot of recent items. Bumped a tier
          (440->500) so the bigger row fonts have breathing room. Each
          card's columns scroll internally for overflow. Stacks
          vertically on narrow viewports via the `lg:` breakpoint. */}
      {/* Two decision rows:
          1. Alerts (full width, TopStocks+Feed+PerIndice side-by-side
             internally — earlier "react" pane).
          2. Discovery row: TopPicks (score-based) + SuperinvestorPicks
             (consensus-based). 2 columns at lg+, stacked below.
          AlertsCompactPanel has 3 internal sub-columns that overflow
          when squeezed to 1/3 of the viewport, so giving it the full
          row keeps it readable. */}
      {summaryData && (
        <div className="lg:h-[420px]">
          <AlertsCompactPanel
            topStocks={summaryData.top_stocks_30d}
            recentAlerts={summaryData.recent_alerts}
            alertsByIndex={summaryData.alerts_by_index_30d}
            alertsLast24h={summaryData.kpis.alerts_last_24h}
            alertsPrev24h={summaryData.kpis.alerts_prev_24h}
          />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:h-[420px]">
        <div className="lg:h-full lg:min-h-0">
          <TopPicksCard />
        </div>
        <div className="lg:h-full lg:min-h-0">
          <SuperinvestorPicksCard />
        </div>
      </div>
      <DataSourcesCard />
      {summaryData && <SystemStatusFooter status={summaryData.system_status} />}
    </div>
  );
}
