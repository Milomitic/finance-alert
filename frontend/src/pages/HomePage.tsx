import { AlertCircle, Clock, RefreshCw } from "lucide-react";
import { Suspense, lazy } from "react";

import { AlertsCompactPanel } from "@/components/dashboard/AlertsCompactPanel";
import { BreadthMatrixTable } from "@/components/dashboard/BreadthMatrixTable";
import { MarketMoodStrip } from "@/components/dashboard/MarketMoodStrip";
import { LiveVolumeMoversCard } from "@/components/dashboard/LiveVolumeMoversCard";
import { MarketEventsRail } from "@/components/dashboard/MarketEventsRail";
import { MarketTickerTape } from "@/components/dashboard/MarketTickerTape";
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
import { FirstPaintGate } from "@/components/ui/first-paint-gate";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";
import { useMarketSummary } from "@/hooks/useMarketSummary";

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
  // One thin bar: the mood hero is a strip now, not a 340px row.
  return <CardSkeleton className="h-[52px]" rows={1} />;
}

function SpotlightRowSkeleton() {
  return (
    // Mirrors the real row: 2×2 below dense-4, four across above it. The
    // skeleton has to use the SAME breakpoints as the loaded layout, or the
    // page visibly reflows the moment data lands — which is exactly what the
    // first-paint gate exists to prevent.
    <div className="grid gap-3 dense-3:grid-cols-[19fr_19fr_12fr] [&>*]:min-w-0">
      <CardSkeleton label="TOP MOVERS" rows={10} strongHeader className="h-[400px]" />
      <CardSkeleton label="VOLUMI MAGGIORI" rows={10} strongHeader className="h-[400px]" />
      <CardSkeleton label="SINTESI EVENTI" rows={10} strongHeader className="h-[400px]" />
    </div>
  );
}

function BreadthRowSkeleton() {
  return (
    // Lower row: breadth (wide, bottom-left) + RSI + Sectors (lg:h-[520px]).
    <div className="grid grid-cols-1 md:grid-cols-2 dense-3:grid-cols-[2fr_1fr_1fr] gap-3 dense-3:h-[520px] [&>*]:min-w-0">
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
      <AlertsPanelSkeleton />
      <SpotlightRowSkeleton />
      <BreadthRowSkeleton />
      {/* Discovery row: [2fr_1fr_1fr] at lg+. */}
      <div className="grid grid-cols-1 dense-3:grid-cols-[2fr_1fr_1fr] gap-3 dense-3:h-[420px] [&>*]:min-w-0">
        <CardSkeleton label="TOP PICKS" rows={10} strongHeader />
        <CardSkeleton label="SUPERINVESTOR" rows={8} strongHeader />
        <CardSkeleton label="VALUTAZIONI ANALISTI" rows={8} strongHeader />
      </div>
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

function HomePageContent() {
  const market = useMarketSummary();
  const summary = useDashboardSummary();
  // The pre-market query no longer lives here: MarketEventsRail owns it,
  // along with the strict `available` gate (US market closed AND cache fresh
  // AND non-empty) that decides whether the section renders at all. The page
  // no longer has to reshape its grid around a card that may or may not
  // appear — the rail is always present and its pre-market section is not.

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
        <MarketMoodStrip global={m.global} byIndex={m.by_index} />
      ) : (
        <HeroRowSkeleton />
      )}
      {/* Segnali, above the fold.
       *
       * The app is called finance-ALERT and this is the panel that says what
       * fired: new signals, the confluence clusters, the names carrying them.
       * It used to sit at the very bottom, five screens down, under four rows
       * of market description — so the thing the product exists to surface was
       * the last thing the page showed. Ordering is an editorial claim about
       * what matters, and the old order made the wrong one.
       *
       * Market context did not disappear, it moved behind: the strip above
       * carries the verdict, and breadth / RSI / sectors are one scroll down
       * for when the answer to "what fired" prompts "in what weather". */}
      {/* Height follows the panel's own column count, which is 2 up to dense-4
          and 4 above it — a 2-column panel needs roughly twice the rows, so a
          single cap wrong-foots one of the two. Leaving it uncapped was worse
          still: measured, the page grew from 5.4 to 6.0 screens at 1280px, and
          the whole point of moving Segnali up was to make the page shorter. */}
      {summaryData ? (
        <div className="md:h-[520px] dense-4:h-[420px]">
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
      {/* Activity row — two protagonists and a rail.
       *
       * This used to be four equal cards (52w events, Volumi, Top movers,
       * Pre-market), which is four lists answering one question: what moved
       * today. It read as density, but it was partly duplication — the lists
       * rank by dollar volume or market cap, so the same mega-caps surfaced in
       * several of them at once (META appeared in four cards simultaneously,
       * AAPL/AMZN/MSFT/NVDA/GOOGL in three each; 23 tickers of 129 were
       * repeated).
       *
       * The split above cost more than it bought. With four cards on one row a
       * 1280px viewport gave each ~230px, and a movers row spends 241px on
       * fixed numeric columns before the name gets a pixel — so the name
       * resolved to 0px. The page was, in effect, choosing what to drop, and
       * choosing badly and invisibly.
       *
       * So the hierarchy is stated instead of inferred. Top movers and Volumi
       * are the two lists actually read every day: they get real width and
       * complete rows at every viewport (TopMovers switches to `stacked`, so
       * each row spans the whole card and keeps all six columns even at
       * 1280px). 52w events, volume spikes and pre-market fold into
       * MarketEventsRail — always visible, never behind a tab, reduced on
       * purpose to ticker + one number.
       *
       * Three geometries, one per amount of room. At dense-3 the rail is a
       * narrow third column. Between md and dense-3 only two cards fit, so the
       * rail drops below them at full width and lays its sections out
       * horizontally — shorter than three stacked cards, which is what a naive
       * `grid-cols-1` fallback produced (measured: the page got TALLER at
       * 1280px than before the change). Below md everything stacks. */}
      {m?.movers ? (
        <div className="grid gap-3 md:grid-cols-2 dense-3:grid-cols-[19fr_19fr_12fr] items-stretch [&>*]:min-w-0">
          <div className="min-w-0">
            <TopMoversCard movers={m.movers} computedAt={m.computed_at} layout="stacked" />
          </div>
          <div className="min-w-0">
            <LiveVolumeMoversCard movers={m.movers} computedAt={m.computed_at} />
          </div>
          <div className="min-w-0 md:col-span-2 dense-3:col-span-1">
            <MarketEventsRail movers={m.movers} />
          </div>
        </div>
      ) : (
        <SpotlightRowSkeleton />
      )}
      {/* Lower row: breadth matrix (bottom-left, wide 2fr) + RSI + Sectors.
          Three across only at dense-3 (1400px). At lg the two 1fr cards were
          235px, narrower than "Information Technology" needs to render (156px
          of text plus its value), so sector labels and the RSI legend clipped.
          The fixed row height moves with the column count for the same reason:
          at 2 columns the row is twice as tall, and a height pinned at lg
          would crop it. */}
      {m?.by_index && m.rsi_distribution && m.sectors ? (
        <div
          id="breadth"
          className="grid grid-cols-1 md:grid-cols-2 dense-3:grid-cols-[2fr_1fr_1fr] gap-3 dense-3:h-[520px] [&>*]:min-w-0 scroll-mt-4"
        >
          <div className="h-[440px] dense-3:h-full min-h-0"><BreadthMatrixTable data={m.by_index} /></div>
          <div className="h-[440px] dense-3:h-full min-h-0">
            <Suspense fallback={<CardSkeleton label="RSI DISTRIBUTION" rows={6} className="h-full" />}>
              <RsiHistogramCard rsi={m.rsi_distribution} indices={m.by_index} />
            </Suspense>
          </div>
          <div className="h-[440px] dense-3:h-full min-h-0"><SectorsHeatmapCard sectors={m.sectors} /></div>
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
      {/* dense-3, not lg — and this row had the worst of it. TopPicks takes
          2fr and then splits INTERNALLY into three tiers
          (Conservative/Moderate/Aggressive), so at lg its 469px became three
          sub-columns of ~155px and the ticker column resolved to 0px: the
          tier lists rendered their rows with no ticker at all. Two columns
          between md and dense-3 gives TopPicks a full row of its own. */}
      <div className="grid grid-cols-1 dense-3:grid-cols-[2fr_1fr_1fr] gap-3 dense-3:h-[420px] [&>*]:min-w-0">
        {/* No fixed mobile height: TopPicksCard flows its 3 tiers
            (24 rows) at natural height and the page scrolls. A capped
            height here would crush the rows (text overlap). dense-3+: fills
            the row height as before. */}
        <div className="dense-3:h-full dense-3:min-h-0">
          <TopPicksCard />
        </div>
        <div className="h-[420px] dense-3:h-full dense-3:min-h-0">
          <SuperinvestorPicksCard />
        </div>
        <div className="h-[420px] dense-3:h-full dense-3:min-h-0">
          <AnalystActionsCard />
        </div>
      </div>
    </div>
  );
}

/* The gate wraps the whole page rather than each panel: the point is to stop
 * the panels appearing one at a time, which per-panel skeletons cannot do —
 * they ARE the stagger, just prettier.
 *
 * This was removed twice on the belief that it was blanking the dashboard. It
 * was not: the blank screen came from a hook called after an early return in
 * RunProgressToast, which unmounted the whole tree (fixed in 76bd68a, and the
 * console named it precisely both times nobody read it). The gate is restored
 * unchanged. It is also no longer the last line of defence — Layout wraps the
 * route outlet in an ErrorBoundary, so a crash under here costs this subtree
 * rather than the page.
 */
export default function HomePage() {
  return (
    <FirstPaintGate>
      <HomePageContent />
    </FirstPaintGate>
  );
}

