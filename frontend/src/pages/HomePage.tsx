import { AlertCircle, Clock, RefreshCw } from "lucide-react";

import { AlertsCompactPanel } from "@/components/dashboard/AlertsCompactPanel";
import { BreadthMatrixTable } from "@/components/dashboard/BreadthMatrixTable";
import { FiftyTwoWeekVolCard } from "@/components/dashboard/FiftyTwoWeekVolCard";
import { HeroStrip } from "@/components/dashboard/HeroStrip";
import { LiveVolumeMoversCard } from "@/components/dashboard/LiveVolumeMoversCard";
import { MarketTickerTape } from "@/components/dashboard/MarketTickerTape";
import { PremarketMoversCard } from "@/components/dashboard/PremarketMoversCard";
import { AnalystActionsCard } from "@/components/dashboard/AnalystActionsCard";
import { ConfluenceCard } from "@/components/dashboard/ConfluenceCard";
import { ScanHeaderButton } from "@/components/dashboard/ScanHeaderButton";
import { TopMoversCard } from "@/components/dashboard/TopMoversCard";
import { TopPicksCard } from "@/components/dashboard/TopPicksCard";
import { RsiHistogramCard } from "@/components/dashboard/RsiHistogramCard";
import { SectorsHeatmapCard } from "@/components/dashboard/SectorsHeatmapCard";
import { SuperinvestorPicksCard } from "@/components/dashboard/SuperinvestorPicksCard";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { usePremarketMovers } from "@/hooks/usePremarketMovers";

/**
 * First-paint loading skeleton for the dashboard. The structure
 * mirrors the loaded layout EXACTLY — same outer grids, same row
 * heights, same column templates — so the transition loaded→data
 * just fills in content rather than reflowing the page. This was a
 * deliberate replacement of the previous "generic boxes grid"
 * skeleton (3 hero + 1 big + 4 mini) which did NOT match the final
 * structure and caused a visible jump.
 */
function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      {/* HeroStrip row: [340px_1fr_200px] split at lg+. */}
      <div className="grid gap-3 lg:grid-cols-[340px_1fr_200px]">
        <CardSkeleton className="h-[120px]" rows={3} />
        <CardSkeleton label="MERCATI LIVE" rows={4} strongHeader className="h-[120px]" />
        <CardSkeleton className="h-[120px]" rows={3} />
      </div>
      {/* Row 2: Volumi + 52w (top-left pair) + TopMovers, with pre-market
          on the right — mirrors the real row template. */}
      <div className="grid gap-3 lg:grid-cols-[3fr_2fr] lg:h-[440px]">
        <div className="grid gap-3 lg:grid-cols-3">
          <CardSkeleton label="VOLUMI" rows={8} strongHeader className="h-[400px]" />
          <CardSkeleton label="52 SETTIMANE" rows={8} strongHeader className="h-[400px]" />
          <CardSkeleton label="TOP MOVERS" rows={8} strongHeader className="h-[400px]" />
        </div>
        <CardSkeleton label="PRE-MARKET USA" rows={8} strongHeader className="h-[400px]" />
      </div>
      {/* Lower row: breadth (wide, bottom-left) + RSI + Sectors (lg:h-[520px]). */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[520px]">
        <CardSkeleton label="BREADTH PER INDICE" rows={8} strongHeader />
        <CardSkeleton label="RSI DISTRIBUTION" rows={6} strongHeader />
        <CardSkeleton label="SETTORI" rows={6} strongHeader />
      </div>
      {/* Discovery row: [2fr_1fr_1fr] at lg+. */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[420px]">
        <CardSkeleton label="TOP PICKS" rows={10} strongHeader />
        <CardSkeleton label="SUPERINVESTOR" rows={8} strongHeader />
        <CardSkeleton label="VALUTAZIONI ANALISTI" rows={8} strongHeader />
      </div>
      {/* Alerts panel — single-row, fixed height. */}
      <CardSkeleton label="SEGNALI" rows={8} strongHeader className="lg:h-[420px]" />
      {/* Footer (DataSources). */}
      <CardSkeleton label="DATA SOURCES" rows={3} className="h-[120px]" />
    </div>
  );
}

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
  // The pre-market card is visible ONLY when the backend tells us
  // `available=true` — i.e. the US regular market is CLOSED AND the
  // pre-market cache is fresh AND non-empty. Any other state (RTH
  // open / cache cold / fetch in flight / no data) hides the card
  // entirely AND collapses the surrounding grid so the breadth +
  // top-movers row takes the full row width (no dead column).
  //
  // Evolution: earlier we kept the slot visible during cache-cold
  // off-hours with a "in attesa" placeholder, but the user
  // requested that the card appear only when there's actually
  // something to show. Hiding the slot is the strictest possible
  // surface — no flash of empty boxes, no "perché non si carica?"
  // moment, just "card appears when data exists".
  //
  // While the hook is in flight `premarketQ.data` is undefined →
  // `available` is undefined → `!!undefined` is false → we default
  // to HIDE. The hook has staleTime=5s + a shared cache so on
  // subsequent navigations data is usually already populated.
  const premarketQ = usePremarketMovers();
  const hidePremarket = !premarketQ.data?.available;

  // First-paint loading skeleton — mirrors the loaded layout 1:1 so
  // the transition is a *fill-in*, not a reflow. See DashboardSkeleton
  // for the structural rationale.
  if (market.isLoading || summary.isLoading) {
    return <DashboardSkeleton />;
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
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 min-w-0">
          <h2 className="text-base font-semibold tracking-tight">Dashboard</h2>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
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
      {/* Row 2: breadth (left) + live-volume + (when available) the
          US pre-market card to the RIGHT of live-volume. Pre-market
          shown → 3 columns with breadth narrowed (2fr vs 3fr); not
          shown → original 2-column split, no empty track. */}
      {/* Pre-market-aware row. Two layouts, both pixel-locked to the
          HeroStrip `[3fr_2fr]` boundary above so each card's right
          edge aligns with the matching card in the row above:
            - Pre-market NOT available (RTH open OR cache cold OR no
              data): card hidden. Row is a flat `[3fr_2fr]` → Breadth
              (left, ~60% — aligns with MoodCard edges) + TopMovers
              (right, ~40% — aligns with the "MERCATI LIVE" card
              edges). Gate predicate updated 2026-05: was `market_open`
              (RTH only), now `available` (strict "we have data to
              show right now") per user request to never display the
              card with a placeholder body.
            - Pre-market AVAILABLE: outer `[3fr_2fr]` brings the
              pre-market card in on the right (same 2fr as MERCATI
              LIVE upstairs); inner `[1fr_1fr]` splits Breadth +
              TopMovers evenly within the left 3fr. */}
      {/* Row 2 (prominent): Volumi maggiori + 52w-events promoted to the
          top-left pair, with TopMovers (+ pre-market when available) on the
          right. The breadth matrix moved DOWN to the row below. */}
      {hidePremarket ? (
        <div className="grid gap-3 lg:grid-cols-[3fr_2fr] lg:h-[440px]">
          <div className="grid gap-3 lg:grid-cols-[1fr_1fr] min-h-0">
            <div className="h-[440px] lg:h-full min-h-0"><LiveVolumeMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
            <div className="h-[440px] lg:h-full min-h-0"><FiftyTwoWeekVolCard movers={m.movers} /></div>
          </div>
          <div className="h-[440px] lg:h-full min-h-0"><TopMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-[3fr_2fr] lg:h-[440px]">
          <div className="grid gap-3 lg:grid-cols-3 min-h-0">
            <div className="h-[440px] lg:h-full min-h-0"><LiveVolumeMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
            <div className="h-[440px] lg:h-full min-h-0"><FiftyTwoWeekVolCard movers={m.movers} /></div>
            <div className="h-[440px] lg:h-full min-h-0"><TopMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
          </div>
          <div className="h-[440px] lg:h-full min-h-0"><PremarketMoversCard /></div>
        </div>
      )}
      {/* Lower row: breadth matrix (bottom-left, wide 2fr) + RSI + Sectors. */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[520px]">
        <div className="h-[440px] lg:h-full min-h-0"><BreadthMatrixTable data={m.by_index} /></div>
        <div className="h-[440px] lg:h-full min-h-0"><RsiHistogramCard rsi={m.rsi_distribution} indices={m.by_index} /></div>
        <div className="h-[440px] lg:h-full min-h-0"><SectorsHeatmapCard sectors={m.sectors} /></div>
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
      {/* Discovery row (moved ABOVE Alerts per user request): three
          complementary "what looks good" surfaces side-by-side —
          score-based picks, superinvestor consensus, and the latest
          analyst rating actions on the pool. 3 columns at lg+, stacked
          below. Placed before Alerts so the page reads "discover →
          react" top-to-bottom. */}
      {/* Asymmetric split: TopPicks renders 3 internal sub-columns
          (Conservative/Moderate/Aggressive) so it needs ~2x the width
          of the single-column Superinvestor + Analyst lists to stay
          readable. `[2fr_1fr_1fr]` keeps the sub-columns legible while
          still fitting the new third card on the same row. */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[420px]">
        {/* No fixed mobile height: TopPicksCard flows its 3 tiers
            (24 rows) at natural height and the page scrolls. A capped
            height here would crush the rows (text overlap). lg+: fills
            the row height as before. */}
        <div className="lg:h-full lg:min-h-0">
          <TopPicksCard />
        </div>
        <div className="h-[420px] lg:h-full lg:min-h-0">
          <SuperinvestorPicksCard />
        </div>
        <div className="h-[420px] lg:h-full lg:min-h-0">
          <AnalystActionsCard />
        </div>
      </div>
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
      <div className="lg:h-[340px]">
        <ConfluenceCard />
      </div>
    </div>
  );
}
