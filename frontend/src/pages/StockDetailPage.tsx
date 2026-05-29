import { AlertCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import type { LiveQuote, OhlcvBar, PriceAlert } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { useChartSync } from "@/hooks/useChartSync";
import { liveExtendIndicators } from "@/lib/liveIndicators";
import { useCreatePriceAlert, useStockPriceAlerts } from "@/hooks/useStockPriceAlerts";
import { useLiveQuote } from "@/hooks/useLiveQuote";
import { useStockDetail } from "@/hooks/useStockDetail";
import { useStockDrawings } from "@/hooks/useStockDrawings";
import { AnalystTargetCard } from "@/components/stock/AnalystTargetCard";
import { CompanyOverviewCard } from "@/components/stock/CompanyOverviewCard";
import { DrawingToolbar, type DrawingMode } from "@/components/stock/DrawingToolbar";
import { FundamentalsCard } from "@/components/stock/FundamentalsCard";
import { InsidersAnalystCard } from "@/components/stock/InsidersAnalystCard";
import { InstitutionalHoldersCard } from "@/components/stock/InstitutionalHoldersCard";
import { MicroDataCard } from "@/components/stock/MicroDataCard";
import {
  DEFAULT_INDICATOR_STATE,
  IndicatorToggles,
  type IndicatorKey, type IndicatorState, type IndicatorStyle,
} from "@/components/stock/IndicatorToggles";
import { MacdPanel } from "@/components/stock/MacdPanel";
import { NewsCard } from "@/components/stock/NewsCard";
import { PriceAlertDialog } from "@/components/stock/PriceAlertDialog";
// PriceAlertsCard removed from the layout (per user feedback) — its
// slot in the right sidebar now hosts InsidersAnalystCard. Price-alert
// CRUD via dialog/chart-click still works (the import is no longer
// needed here because nothing on this page lists existing alerts).
import { PriceChart } from "@/components/stock/PriceChart";
import { RangeSelector } from "@/components/stock/RangeSelector";
import { ResizableSection } from "@/components/stock/ResizableSection";
import { RsiPanel } from "@/components/stock/RsiPanel";
import { StockAlertsHistoryCard } from "@/components/stock/StockAlertsHistoryCard";
import { StockHeader } from "@/components/stock/StockHeader";
import { EtfHoldingsCard } from "@/components/stock/EtfHoldingsCard";
import { StockScoreCard } from "@/components/stock/StockScoreCard";
import { StockTechnicalCard } from "@/components/stock/StockTechnicalCard";
import { TechnicalKpiCard } from "@/components/stock/TechnicalKpiCard";

/**
 * Merge the live quote into the OHLCV series so the rightmost candle
 * reflects the in-session price instead of yesterday's close.
 *
 * Why this is needed: for 1d/1w/1m/all the backend reads daily bars
 * from the DB, and those are only refreshed by the EOD scan at 23:30.
 * During the trading day the latest stored bar is yesterday's close —
 * the chart's last candle would otherwise lag the live header price.
 *
 *  - 1d: if last.date is older than today, APPEND a new bar dated
 *    today with open/high/low/close synthesized from the live quote.
 *  - 1w / 1m / all: the last bar covers a multi-day range that
 *    includes today, so UPDATE its close (= live price) and extend
 *    high/low with today's session extremes.
 *
 * Intraday timeframes (30m / 1h) are excluded: those come straight
 * from yfinance and already include today's partial bar with live
 * values. Volume is intentionally left untouched for 1w/1m/all to
 * avoid double-counting today if the catalog refresh already folded
 * it into the partial bar.
 */
function mergeLiveQuoteIntoOhlcv(
  ohlcv: OhlcvBar[],
  live: LiveQuote | undefined,
  range: string,
): OhlcvBar[] {
  if (range === "5m" || range === "30m" || range === "1h") return ohlcv;
  if (!live || live.price == null || ohlcv.length === 0) return ohlcv;
  const todayISO = new Date().toISOString().slice(0, 10);
  // Overlay the live quote whenever the backend says `price` is TODAY's
  // value — either a genuine open session (market_state OPEN/PRE) OR the
  // post-close gap where the backend now serves today's official/
  // provisional close (as_of_date === today). When `price` is yesterday's
  // close (as_of_date < today, e.g. no today data available) we DON'T
  // overlay: appending an echo of the last DB bar would just duplicate
  // the rightmost candle (the original phantom-candle bug).
  const showsToday =
    live.market_state === "OPEN" ||
    live.market_state === "PRE" ||
    live.as_of_date === todayISO;
  if (!showsToday) return ohlcv;

  const last = ohlcv[ohlcv.length - 1];
  const liveOpen = live.day_open ?? live.price;
  const liveHigh = Math.max(live.day_high ?? live.price, live.price);
  const liveLow = Math.min(live.day_low ?? live.price, live.price);

  if (range === "1d" && last.date < todayISO) {
    return [
      ...ohlcv,
      {
        date: todayISO,
        open: liveOpen,
        high: liveHigh,
        low: liveLow,
        close: live.price,
        volume: live.volume ?? 0,
      },
    ];
  }
  return [
    ...ohlcv.slice(0, -1),
    {
      ...last,
      close: live.price,
      high: Math.max(last.high, liveHigh),
      low: Math.min(last.low, liveLow),
    },
  ];
}

export default function StockDetailPage() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  // v2 timeframe vocabulary: default to 1d (was "1y" range). Backend
  // accepts 30m/1h/1d/1w/1m/all, with legacy keys (incl. 4h) still
  // mapped for bookmarked URLs. See `services/timeframe_service`.
  const range = searchParams.get("range") ?? "1d";

  const detail = useStockDetail(ticker, range);
  const priceAlertsQuery = useStockPriceAlerts(ticker);
  const createPa = useCreatePriceAlert(ticker);
  const drawings = useStockDrawings(ticker);
  // Live quote drives the chart's rightmost candle merge (see
  // mergeLiveQuoteIntoOhlcv). The query is also used by StockHeader;
  // both calls share the same React-Query cache entry so this doesn't
  // duplicate the upstream yfinance request.
  const live = useLiveQuote(ticker);
  const mergedOhlcv = useMemo(
    () => mergeLiveQuoteIntoOhlcv(detail.data?.ohlcv ?? [], live.data, range),
    [detail.data?.ohlcv, live.data, range],
  );
  // Extend the backend (EOD) indicator series with a live tail so EMA / BB /
  // RSI / MACD reach the same in-session candle the chart shows. Patches only
  // the last point — history is left exactly as the backend computed it.
  const liveIndicators = useMemo(
    () =>
      detail.data ? liveExtendIndicators(detail.data.indicators, mergedOhlcv) : null,
    [detail.data, mergedOhlcv],
  );

  const [indicators, setIndicators] = useState<IndicatorState>(DEFAULT_INDICATOR_STATE);
  const [mode, setMode] = useState<DrawingMode>("none");
  const [pendingPrice, setPendingPrice] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  // Line tool: the first clicked point, awaiting the second click that
  // completes the trend line. Cleared whenever we leave "trend" mode.
  const [pendingTrend, setPendingTrend] = useState<{ x: number; y: number } | null>(null);
  useEffect(() => {
    if (mode !== "trend") setPendingTrend(null);
  }, [mode]);

  // Chart-sync orchestrator: PriceChart + RsiPanel + MacdPanel each
  // register with this on mount, the hook then forwards every pan/zoom
  // event from any one chart to the others so the time axis stays
  // anchored across the stack. Stable across renders — safe to pass as
  // a prop without re-mounting the children.
  const registerChart = useChartSync();

  const onIndicatorChange = (key: IndicatorKey, next: IndicatorStyle) =>
    setIndicators((prev) => ({ ...prev, [key]: next }));

  const handleChartClick = (price: number, time?: number) => {
    if (mode === "alert") {
      setPendingPrice(price);
      setDialogOpen(true);
      setMode("none");
    } else if (mode === "hline") {
      drawings.addHorizontal(Math.round(price * 100) / 100);
      setMode("none");
    } else if (mode === "trend") {
      // Two-click line: capture the first (time, price), then on the
      // second click commit the segment and exit the tool. `time` is the
      // bar's UTC-seconds timestamp; clicks off the data range are ignored.
      if (time == null) return;
      if (!pendingTrend) {
        setPendingTrend({ x: time, y: price });
      } else if (time !== pendingTrend.x) {
        // Need two DISTINCT bars — a same-bar (vertical) segment has
        // duplicate timestamps which a line series can't render.
        drawings.addTrend(pendingTrend.x, pendingTrend.y, time, price);
        setPendingTrend(null);
        setMode("none");
      }
    }
  };

  // First-paint skeleton — mirrors the stock-detail layout so the
  // transition loaded→data fills in content rather than reflowing. The
  // page is essentially `[1fr_320px]` (main chart column + right
  // sidebar of context cards) under a sticky header.
  if (detail.isLoading) {
    return (
      <div className="space-y-3">
        {/* Header strip: ticker / live price / score chips */}
        <CardSkeleton label={ticker?.toUpperCase()} rows={2} className="h-[100px]" />
        <div className="grid lg:grid-cols-[1fr_320px] gap-3">
          <div className="space-y-3">
            {/* Main chart placeholder — matches the PriceChart's tall slot. */}
            <CardSkeleton label="GRAFICO PREZZO" rows={10} strongHeader className="h-[600px]" />
            {/* Below-chart row: 3 ~equal-height context cards. */}
            <div className="grid lg:grid-cols-3 gap-3">
              <CardSkeleton label="FONDAMENTALI" rows={6} strongHeader className="h-[260px]" />
              <CardSkeleton label="VALUTAZIONE" rows={6} strongHeader className="h-[260px]" />
              <CardSkeleton label="NEWS" rows={6} strongHeader className="h-[260px]" />
            </div>
          </div>
          <div className="space-y-3">
            <CardSkeleton label="OVERVIEW" rows={5} strongHeader className="h-[200px]" />
            <CardSkeleton label="SCORE" rows={6} strongHeader className="h-[260px]" />
            <CardSkeleton label="ANALYST TARGET" rows={5} strongHeader className="h-[200px]" />
            <CardSkeleton label="SUPERINVESTOR / FONDI" rows={6} strongHeader className="h-[260px]" />
            <CardSkeleton label="INSIDER / ANALISTI" rows={5} strongHeader className="h-[200px]" />
          </div>
        </div>
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <Card>
        <CardContent className="p-6 flex items-center gap-3 text-sm">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <span>Errore nel caricamento del ticker <strong>{ticker}</strong>. Verifica che esista in catalogo.</span>
        </CardContent>
      </Card>
    );
  }

  const d = detail.data;
  // Live-extended indicator series (falls back to the raw backend series).
  const ind = liveIndicators ?? d.indicators;
  const priceAlerts: PriceAlert[] = priceAlertsQuery.data ?? [];
  const lastClose = d.kpis.last_close ?? 0;

  const hasMacd = (d.indicators.macd_line?.length ?? 0) > 0;

  return (
    <div className="space-y-3">
      {/* Top hero row (test layout): identity/price header on the left, with
          the Stock score + Technical score cards beside it on the right.
          `card principale — card score — card score tecnico`. items-start so
          the short header keeps its natural height next to the taller score
          cards. */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr_1fr] gap-3 items-start">
        <StockHeader
          stock={d.stock}
          kpis={d.kpis}
          ohlcv={mergedOhlcv}
        />
        <StockScoreCard ticker={ticker} />
        <StockTechnicalCard ticker={ticker} />
      </div>

      {/* ETF components — renders only for ETFs (null for equities), so
          for a fund it sits right under the hero as the lead content:
          per-component weight, trend sparkline, price + day variation. */}
      <EtfHoldingsCard ticker={ticker} />

      {/* Company overview (left, 67%) + Alert storici (right, 33%).
          Equal-height row (`items-stretch`, the grid default): the
          alerts card fills the height set by the company-profile prose
          and scrolls internally when there are more rows than fit.
          The profile is the page's lead content and dictates the row
          height; the alerts card adapts. Stacks vertically below `lg`. */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3 lg:h-[300px]">
        {/* Both cards fill the fixed row height (h-full inside each): the
            profile's prose scrolls internally if its condensed summary still
            overflows, the alerts card scrolls its rows. AlertsHistory needs a
            concrete mobile height too, else its `flex-1 min-h-0` pane collapses
            to 0 without the row's `lg:h-[300px]`. */}
        <div className="lg:h-full lg:min-h-0">
          <CompanyOverviewCard ticker={ticker} stock={d.stock} />
        </div>
        <div className="h-[300px] lg:h-full lg:min-h-0">
          <StockAlertsHistoryCard alerts={d.alerts_history} />
        </div>
      </div>

      {/* Four side-by-side cards: Fundamentals | Valuation+KPIs | News | Analyst.
          Weighted columns `[1.5fr_1fr_1fr_1fr]` give Fundamentals ~33% (it has
          a 7-column earnings table that needs the breathing room) and the
          other three each ~22%.
          Fixed `lg:h-[520px]` row height (was 640): tighter so the row
          doesn't dominate the viewport. All four cards have proper
          internal scroll — Fundamentals scrolls its earnings table,
          Valuation scrolls its now-much-longer metrics list (~50 rows
          across 2 columns after the yfinance expansion), News scrolls
          its items, Analyst scrolls its recent actions. */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr_1fr_1fr] gap-3 lg:h-[520px]">
        {/* Fundamentals: no internal scroll — its earnings table sets
            the natural height (CLAUDE.md). Leave it auto on mobile.
            The other three scroll internally so they need an explicit
            mobile height to not collapse. NewsCard is internally
            `relative h-full` + absolute-inset child, so a fixed-height
            wrapper is exactly the containing block it needs. */}
        <div className="lg:h-full lg:min-h-0">
          <FundamentalsCard ticker={ticker} />
        </div>
        <div className="h-[520px] lg:h-full lg:min-h-0">
          <MicroDataCard ticker={ticker} stock={d.stock} kpis={d.kpis} />
        </div>
        <div className="h-[520px] lg:h-full lg:min-h-0">
          <NewsCard ticker={ticker} />
        </div>
        <div className="h-[480px] lg:h-full lg:min-h-0">
          <AnalystTargetCard ticker={ticker} />
        </div>
      </div>

      {/* The dedicated Alerts + Insiders row that used to live here was
          decomposed: alerts moved next to the company profile (above),
          insiders moved into the right-hand sidebar (below) so the
          chart can dominate the vertical real estate that the row
          used to consume. */}

      <div className="grid lg:grid-cols-[1fr_480px] gap-3">
        <Card>
          <CardContent className="p-4">
            {/* Single-row toolbar with three balanced clusters: timeframe
                pinned LEFT, indicators CENTERED, drawing tools pinned
                RIGHT. The centering is done with `mx-auto` on the middle
                group — in a flex row its two auto margins split the free
                space equally, so the indicators sit centred between the
                left/right clusters (and wrap gracefully when space runs
                out). All controls share the 32px (h-8) height. */}
            <div className="flex items-center flex-wrap gap-x-3 gap-y-2 mb-3">
              {/* LEFT — timeframe */}
              <RangeSelector
                value={range}
                onChange={(r) => setSearchParams({ range: r })}
              />
              {/* CENTER — indicators */}
              <div className="mx-auto flex items-center gap-2 flex-wrap justify-center">
                <span className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground/70 shrink-0 hidden md:block">
                  Indicatori
                </span>
                <IndicatorToggles
                  state={indicators}
                  onChange={onIndicatorChange}
                  periods={d.indicators.periods}
                />
              </div>
              {/* RIGHT — drawing tools (+ live hint for the Line tool) */}
              <div className="flex items-center gap-2.5 shrink-0">
                {mode === "trend" && (
                  <span className="text-[11px] font-medium text-blue-600 animate-pulse whitespace-nowrap">
                    {pendingTrend ? "Clicca il 2° punto" : "Clicca il 1° punto"}
                  </span>
                )}
                <DrawingToolbar
                  mode={mode}
                  onSetMode={setMode}
                  onClearAll={drawings.clearAll}
                />
              </div>
            </div>

            {/* Price chart — resizable; defaults to 460px */}
            {mergedOhlcv.length < 2 ? (
              <div className="h-[460px] flex items-center justify-center text-sm text-muted-foreground border border-border/50 rounded-md">
                Dati insufficienti per il chart
              </div>
            ) : (
              <ResizableSection defaultHeight={460} minHeight={240} label="Price">
                {/* `key={range}` forces a clean remount on range switch
                    (1m / 3m / 6m / 1y / 5y / all). Without it, the data
                    effects of all three charts fire fitContent() in
                    arbitrary order and cross-propagate stale logical
                    ranges to each other, "shrinking" the visible window
                    until it stabilizes. Remounting kills the race
                    entirely — fresh chart, fresh data, fit once. */}
                <PriceChart
                  key={range}
                  ohlcv={mergedOhlcv}
                  indicators={ind}
                  styles={{
                    ema20: indicators.ema20,
                    ema50: indicators.ema50,
                    ema200: indicators.ema200,
                    bb: indicators.bb,
                  }}
                  priceAlerts={priceAlerts}
                  horizontalDrawings={drawings.drawings.horizontal}
                  trendDrawings={drawings.drawings.trend}
                  onChartClick={handleChartClick}
                  onReady={registerChart}
                  timeframe={range}
                />
              </ResizableSection>
            )}

            {/* RSI sub-panel — togglable + resizable.
                Default height bumped 140→200 so the 30/70 reference lines
                have room to breathe and the curve isn't squashed.
                Label uses the live period from the API response (e.g.
                "RSI(7)" on a 1m chart, "RSI(21)" on the all-time view). */}
            {indicators.rsi.visible && d.indicators.rsi14.length > 0 && (
              <div className="mt-3">
                <ResizableSection
                  defaultHeight={200}
                  minHeight={80}
                  label={`RSI(${d.indicators.periods?.rsi ?? 14})`}
                >
                  <RsiPanel
                    key={range}
                    rsi14={ind.rsi14}
                    color={indicators.rsi.color}
                    width={indicators.rsi.width}
                    onReady={registerChart}
                  />
                </ResizableSection>
              </div>
            )}

            {/* MACD sub-panel — togglable + resizable.
                Default height bumped 160→220: MACD shows three series
                (line, signal, histogram) that benefit from the extra
                vertical room more than RSI.
                Label reflects live (fast,slow,signal) periods. */}
            {indicators.macd.visible && hasMacd && (
              <div className="mt-3">
                <ResizableSection
                  defaultHeight={220}
                  minHeight={80}
                  label={
                    d.indicators.periods
                      ? `MACD(${d.indicators.periods.macd_fast},${d.indicators.periods.macd_slow},${d.indicators.periods.macd_signal})`
                      : "MACD(12,26,9)"
                  }
                >
                  <MacdPanel
                    key={range}
                    line={ind.macd_line ?? []}
                    signal={ind.macd_signal ?? []}
                    hist={ind.macd_hist ?? []}
                    color={indicators.macd.color}
                    width={indicators.macd.width}
                    onReady={registerChart}
                  />
                </ResizableSection>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-3">
          {/* Stock score + Technical score moved up to the hero row. */}
          <TechnicalKpiCard ticker={ticker} />
          {/* Institutional / superinvestor holders sit ABOVE insiders
              (per user spec): the conviction signal from a 13F-tracked
              fund is more decisive than the insider buy/sell rhythm.
              Empty list still renders a 1-line "no fund holds this"
              note so the sidebar shape doesn't shift between stocks. */}
          <InstitutionalHoldersCard ticker={ticker} />
          {/* InsidersAnalystCard now occupies the slot the PriceAlertsCard
              used to hold. Per user feedback the price-alerts list isn't
              worth a full sidebar card — alerts can still be created via
              chart click, and the user prefers seeing the most-recent
              insider transactions next to the score signal. */}
          <InsidersAnalystCard ticker={ticker} />
        </div>
      </div>

      <PriceAlertDialog
        open={dialogOpen}
        initialPrice={pendingPrice ?? undefined}
        initialDirection={pendingPrice != null && pendingPrice > lastClose ? "above" : "below"}
        onClose={() => setDialogOpen(false)}
        onSubmit={(body) => {
          createPa.mutate(body);
          setDialogOpen(false);
        }}
      />
    </div>
  );
}
