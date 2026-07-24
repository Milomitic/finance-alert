import { AlertCircle, Clock, RefreshCw } from "lucide-react";
import { Suspense, lazy } from "react";

import { AlertsCompactPanel } from "@/components/dashboard/AlertsCompactPanel";
import { BreadthMatrixTable } from "@/components/dashboard/BreadthMatrixTable";
import { FiftyTwoWeekVolCard } from "@/components/dashboard/FiftyTwoWeekVolCard";
import { HeroStrip } from "@/components/dashboard/HeroStrip";
import { LiveVolumeMoversCard } from "@/components/dashboard/LiveVolumeMoversCard";
import { MarketTickerTape } from "@/components/dashboard/MarketTickerTape";
import { PremarketMoversCard } from "@/components/dashboard/PremarketMoversCard";
import { AnalystActionsCard } from "@/components/dashboard/AnalystActionsCard";
import { ScanHeaderButton } from "@/components/dashboard/ScanHeaderButton";
import { TopMoversCard } from "@/components/dashboard/TopMoversCard";
import { TopPicksCard } from "@/components/dashboard/TopPicksCard";
import { SectorsHeatmapCard } from "@/components/dashboard/SectorsHeatmapCard";
import { SuperinvestorPicksCard } from "@/components/dashboard/SuperinvestorPicksCard";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";

// The RSI histogram is the ONLY dashboard consumer of recharts (a ~331KB
// chunk). Lazy-load it so the landing page's critical path ships without the
// charting library; the card pops in right after first paint.
const RsiHistogramCard = lazy(() =>
  import("@/components/dashboard/RsiHistogramCard").then((m) => ({
    default: m.RsiHistogramCard,
  })),
);
import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { usePremarketMovers } from "@/hooks/usePremarketMovers";

/* ─── Per-row skeletons ─────────────────────────────────────────────────── */
/* Each market-driven row has its own skeleton that mirrors the loaded
 * layout EXACTLY — same outer grids, same row heights, same column
 * templates — so the transition loading→data just fills in content
 * rather than reflowing the page. They are composed both by the
 * full-page DashboardSkeleton (first paint, nothing resolved yet) and
 * individually by the main render when ONLY the market summary is
 * still in flight (B4-11 de-waterfall: the dashboard no longer blocks
 * every card behind the slowest of the two summary queries).
 */

function HeroRowSkeleton() {
  return (
    // HeroStrip row: [340px_1fr_200px] split at lg+.
    <div className="grid gap-3 lg:grid-cols-[340px_1fr_200px] [&>*]:min-w-0">
      <CardSkeleton className="h-[120px]" rows={3} />
      <CardSkeleton label="MERCATI LIVE" rows={4} strongHeader className="h-[120px]" />
      <CardSkeleton className="h-[120px]" rows={3} />
    </div>
  );
}

function SpotlightRowSkeleton() {
  return (
    // Row 2: Volumi + 52w (top-left pair) + TopMovers, with pre-market
    // on the right — mirrors the real row template.
    <div className="grid gap-3 lg:grid-cols-[3fr_2fr] lg:h-[440px] [&>*]:min-w-0">
      <div className="grid gap-3 lg:grid-cols-3 [&>*]:min-w-0">
        <CardSkeleton label="VOLUMI" rows={8} strongHeader className="h-[400px]" />
        <CardSkeleton label="52 SETTIMANE" rows={8} strongHeader className="h-[400px]" />
        <CardSkeleton label="TOP MOVERS" rows={8} strongHeader className="h-[400px]" />
      </div>
      <CardSkeleton label="PRE-MARKET USA" rows={8} strongHeader className="h-[400px]" />
    </div>
  );
}

function BreadthRowSkeleton() {
  return (
    // Lower row: breadth (wide, bottom-left) + RSI + Sectors (lg:h-[520px]).
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[520px] [&>*]:min-w-0">
      <CardSkeleton label="BREADTH PER INDICE" rows={8} strongHeader />
      <CardSkeleton label="RSI DISTRIBUTION" rows={6} strongHeader />
      <CardSkeleton label="SETTORI" rows={6} strongHeader />
    </div>
  );
}

function AlertsPanelSkeleton() {
  // Alerts panel — single-row, fixed height.
  return <CardSkeleton label="SEGNALI" rows={8} strongHeader className="lg:h-[420px]" />;
}

/**
 * First-paint loading skeleton for the dashboard, shown ONLY while BOTH
 * summary queries are still on their first fetch with nothing cached.
 * Composed from the per-row skeletons above so the full-page and the
 * per-section variants can never drift apart structurally.
 */
function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      <HeroRowSkeleton />
      <SpotlightRowSkeleton />
      <BreadthRowSkeleton />
      {/* Discovery row: [2fr_1fr_1fr] at lg+. */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[420px] [&>*]:min-w-0">
        <CardSkeleton label="TOP PICKS" rows={10} strongHeader />
        <CardSkeleton label="SUPERINVESTOR" rows={8} strongHeader />
        <CardSkeleton label="VALUTAZIONI ANALISTI" rows={8} strongHeader />
      </div>
      <AlertsPanelSkeleton />
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

  // Full-page skeleton ONLY while BOTH summaries are still on their
  // first load with nothing cached (react-query: `isLoading` =
  // pending first fetch, no cached data). As soon as EITHER resolves
  // we render the real layout and let the still-loading half show its
  // own targeted row skeletons below — previously this was an
  // `isLoading || isLoading` two-stage waterfall that blocked EVERY
  // card (including the self-fetching discovery cards) behind the
  // slower of the two queries.
  if (market.isLoading && summary.isLoading) {
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

  // The "no scan yet" read is only meaningful once the market query has
  // actually settled — while it's still in flight `market.data` is
  // legitimately undefined and we fall through to the layout below,
  // where the market-driven rows render their own skeletons.
  if (!market.isLoading && (!market.data || market.data.available === false)) {
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

  // Happy path — `m` is undefined while the market summary is still in
  // flight (dashboard summary already resolved); the market rows below
  // then show their targeted skeletons. When it IS settled, validate the
  // payload with the same defaults-check as before (all fields are
  // optional in the API type).
  // Note: `treemap` is no longer required (the treemap card was removed) but the API
  // continues to populate it; we just don't render it.
  const m = market.data;
  if (m && (!m.global || !m.by_index || !m.movers || !m.rsi_distribution || !m.sectors)) {
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
            {m?.computed_at && (
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
      {/* Market-driven rows: each renders its own skeleton while the
          market summary is still in flight (the inline field guards
          double as the TS narrowing — past the validation above a
          settled payload always has all of them). */}
      {m?.global && m.by_index ? (
        <HeroStrip global={m.global} byIndex={m.by_index} />
      ) : (
        <HeroRowSkeleton />
      )}
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
      {/* Spotlight row. No fixed height: each card flows to its (capped)
          content and the grid's default `items-stretch` equalizes all
          cards to the tallest one — so there are no internal scrollbars
          and no card is taller than its content needs (snug uniform
          height). See the cards' internals: their lists are natural-height
          (no flex-1/overflow) precisely so this auto-equalization works. */}
      {m?.movers ? (
        hidePremarket ? (
          <div className="grid gap-3 lg:grid-cols-[5fr_4fr] items-stretch [&>*]:min-w-0">
            <div className="grid gap-3 lg:grid-cols-[1fr_1fr] [&>*]:min-w-0">
              <div className="min-w-0"><FiftyTwoWeekVolCard movers={m.movers} /></div>
              <div className="min-w-0"><LiveVolumeMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
            </div>
            <div className="min-w-0"><TopMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
          </div>
        ) : (
          // Flat 4-column grid with CONTENT-PROPORTIONAL widths. The old
          // [5fr_4fr] crammed the three left cards into equal thirds while
          // pre-market alone took 4/9 — so the two-up TopMovers (gainers +
          // losers sub-columns) was squeezed to ~18% and its rows overflowed
          // into each other. The two dense two-column cards (TopMovers,
          // pre-market) now get the most room; the single-column Volumi the
          // least.
          <div className="grid gap-3 lg:grid-cols-[minmax(0,2.2fr)_minmax(0,2fr)_minmax(0,2.9fr)_minmax(0,2.9fr)] items-stretch [&>*]:min-w-0">
            <div className="min-w-0"><FiftyTwoWeekVolCard movers={m.movers} /></div>
            <div className="min-w-0"><LiveVolumeMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
            <div className="min-w-0"><TopMoversCard movers={m.movers} computedAt={m.computed_at} /></div>
            <div className="min-w-0"><PremarketMoversCard /></div>
          </div>
        )
      ) : (
        <SpotlightRowSkeleton />
      )}
      {/* Lower row: breadth matrix (bottom-left, wide 2fr) + RSI + Sectors. */}
      {m?.by_index && m.rsi_distribution && m.sectors ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[520px] [&>*]:min-w-0">
          <div className="h-[440px] lg:h-full min-h-0"><BreadthMatrixTable data={m.by_index} /></div>
          <div className="h-[440px] lg:h-full min-h-0">
            <Suspense fallback={<CardSkeleton label="RSI DISTRIBUTION" rows={6} className="h-full" />}>
              <RsiHistogramCard rsi={m.rsi_distribution} indices={m.by_index} />
            </Suspense>
          </div>
          <div className="h-[440px] lg:h-full min-h-0"><SectorsHeatmapCard sectors={m.sectors} /></div>
        </div>
      ) : (
        <BreadthRowSkeleton />
      )}
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
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-3 lg:h-[420px] [&>*]:min-w-0">
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
      {/* Alerts panel: driven by the dashboard summary alone — shows its
          own skeleton while that query is still in flight instead of
          holding the whole page hostage. Absent (as before) if the
          summary settled without data. */}
      {summaryData ? (
        <div className="lg:h-[420px]">
          <AlertsCompactPanel
            topStocks={summaryData.top_stocks_30d}
            recentAlerts={summaryData.recent_alerts}
            alertsByIndex={summaryData.alerts_by_index_30d}
            alertsLast24h={summaryData.kpis.alerts_last_24h}
            alertsPrev24h={summaryData.kpis.alerts_prev_24h}
          />
        </div>
      ) : summary.isLoading ? (
        <AlertsPanelSkeleton />
      ) : null}
    </div>
  );
}
