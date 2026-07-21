import type { IChartApi } from "lightweight-charts";
import { AlertCircle, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import type { PriceAlert } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { useChartSync } from "@/hooks/useChartSync";
import { liveExtendIndicators } from "@/lib/liveIndicators";
import { mergeLiveQuoteIntoOhlcv } from "@/lib/liveOhlcvMerge";
import { buildEarningsMarkers, buildSignalOverlay } from "@/lib/signalMarkers";
import { rebaseBenchmark } from "@/lib/benchmarkOverlay";
import { downloadChartPng } from "@/lib/chartExport";
import { exchangeTimezone } from "@/lib/exchangeHours";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { useMarketDetail } from "@/hooks/useMarketDetail";
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
import { PriceChart, type ChartType } from "@/components/stock/PriceChart";
import { BENCHMARKS, ChartOptionsToolbar } from "@/components/stock/ChartOptionsToolbar";
import { RangeSelector } from "@/components/stock/RangeSelector";
import { ResizableSection } from "@/components/stock/ResizableSection";
import { RsiPanel } from "@/components/stock/RsiPanel";
import { StockAlertsHistoryCard } from "@/components/stock/StockAlertsHistoryCard";
import { StockHeader } from "@/components/stock/StockHeader";
import { EtfHoldingsCard } from "@/components/stock/EtfHoldingsCard";
import { StockScoreCard } from "@/components/stock/StockScoreCard";
import { StockTechnicalCard } from "@/components/stock/StockTechnicalCard";
import { TechnicalKpiCard } from "@/components/stock/TechnicalKpiCard";

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
  // Stale-intraday detection: last sub-daily bar older than 3 calendar days
  // while the (DB-served) daily feed is fine → upstream intraday gap. The
  // banner above the chart names the cutoff date instead of letting the
  // chart silently end days in the past.
  const staleIntradayDate = useMemo(() => {
    if (!(range === "5m" || range === "30m" || range === "1h")) return null;
    const last = mergedOhlcv[mergedOhlcv.length - 1];
    if (!last?.date) return null;
    const lastMs = new Date(last.date).getTime();
    if (!Number.isFinite(lastMs)) return null;
    const ageDays = (Date.now() - lastMs) / 86_400_000;
    if (ageDays <= 3) return null;
    return new Date(lastMs).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
  }, [mergedOhlcv, range]);
  // Extend the backend (EOD) indicator series with a live tail so EMA / BB /
  // RSI / MACD reach the same in-session candle the chart shows. Patches only
  // the last point — history is left exactly as the backend computed it.
  const liveIndicators = useMemo(
    () =>
      detail.data ? liveExtendIndicators(detail.data.indicators, mergedOhlcv) : null,
    [detail.data, mergedOhlcv],
  );
  // Signal markers overlay: map the stock's alert history onto the chart bars
  // so the user sees WHERE each detector fired (arrow per bar, tone by
  // majority) with a hover panel of detector · Forza · realized outcome.
  const signalOverlay = useMemo(
    () => buildSignalOverlay(mergedOhlcv, detail.data?.alerts_history ?? []),
    [mergedOhlcv, detail.data?.alerts_history],
  );
  // Earnings "E" flags. Reuses the fundamentals query the FundamentalsCard
  // already loads (shared queryKey → no extra request); the earnings list is
  // the report dates + EPS surprise.
  const fundamentals = useStockFundamentals(ticker);
  const earningsMarkers = useMemo(
    () => buildEarningsMarkers(mergedOhlcv, fundamentals.data?.earnings ?? []),
    [mergedOhlcv, fundamentals.data?.earnings],
  );
  // Benchmark overlay: fetch the selected index (same timeframe) via the
  // curated markets endpoint, then rebase its closes onto the stock's start
  // price so the divergence reads as relative performance.
  const [benchmark, setBenchmark] = useState(""); // "" = no overlay
  const chartApiRef = useRef<IChartApi | null>(null);
  const benchmarkDetail = useMarketDetail(benchmark, range);
  const benchmarkLine = useMemo(
    () => (benchmark ? rebaseBenchmark(mergedOhlcv, benchmarkDetail.data?.bars ?? []) : []),
    [benchmark, mergedOhlcv, benchmarkDetail.data?.bars],
  );
  const benchmarkLabel = BENCHMARKS.find((b) => b.symbol === benchmark)?.label;
  // Multi-ticker compare: overlay another stock, rebased the same way. Its
  // range-matched OHLCV comes from the same detail endpoint (enabled only when
  // a ticker is entered).
  const [compareTicker, setCompareTicker] = useState("");
  const compareDetail = useStockDetail(compareTicker, range, !!compareTicker);
  const compareLine = useMemo(
    () => (compareTicker ? rebaseBenchmark(mergedOhlcv, compareDetail.data?.ohlcv ?? []) : []),
    [compareTicker, mergedOhlcv, compareDetail.data?.ohlcv],
  );

  const [indicators, setIndicators] = useState<IndicatorState>(DEFAULT_INDICATOR_STATE);
  const [chartType, setChartType] = useState<ChartType>("candle");
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
      {/* Top hero row: identity/price header (left, 2fr) + the Stock score and
          Technical score cards sharing the right column (1fr, split 50/50).
          The [2fr_1fr] template MATCHES the Company-overview / Segnali row
          below, so the right rail (score+tech above, Segnali below) lines up
          by column — the two score cards together span exactly the Segnali
          card's width. */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3 items-stretch">
        <StockHeader
          stock={d.stock}
          kpis={d.kpis}
          ohlcv={mergedOhlcv}
        />
        <div className="grid grid-cols-2 gap-3 items-stretch">
          <StockScoreCard ticker={ticker} />
          <StockTechnicalCard ticker={ticker} />
        </div>
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
          <StockAlertsHistoryCard alerts={d.alerts_history} ticker={ticker} />
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
              {/* LEFT — timeframe + chart-render options */}
              <RangeSelector
                value={range}
                onChange={(r) => setSearchParams({ range: r })}
              />
              <ChartOptionsToolbar
                chartType={chartType}
                onChartType={setChartType}
                benchmark={benchmark}
                onBenchmark={setBenchmark}
                compareTicker={compareTicker}
                onCompareTicker={setCompareTicker}
                onExport={() =>
                  downloadChartPng(chartApiRef.current, `${ticker}-${range}.png`)
                }
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
                {mode === "erase" && (
                  <span className="text-[11px] font-medium text-red-600 animate-pulse whitespace-nowrap">
                    Clicca una linea da cancellare
                  </span>
                )}
                <DrawingToolbar
                  mode={mode}
                  onSetMode={setMode}
                  onClearAll={drawings.clearAll}
                />
              </div>
            </div>

            {/* Stale-intraday banner: yfinance's intraday endpoint can stop
                serving a symbol while the daily feed stays healthy (observed
                on VSCO, frozen at June 1 upstream). Without this notice the
                chart silently shows days-old candles. >3 calendar days
                tolerates a normal weekend gap (~2.7d Fri close → Mon open). */}
            {staleIntradayDate && (
              <div className="mb-2 flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-600 dark:text-amber-400">
                <span>
                  Dati intraday non disponibili dopo il {staleIntradayDate} (fonte dati).
                </span>
                <button
                  className="underline underline-offset-2 hover:opacity-80"
                  onClick={() => setSearchParams({ range: "1d" })}
                >
                  Passa a 1G per dati aggiornati
                </button>
              </div>
            )}
            {/* Price chart — resizable; defaults to 460px */}
            {mergedOhlcv.length < 2 ? (
              <div className="h-[460px] flex items-center justify-center text-sm text-muted-foreground border border-border/50 rounded-md">
                Dati insufficienti per il chart
              </div>
            ) : (
              <ResizableSection defaultHeight={460} minHeight={240} label="Price">
                {/* Timeframe-switch feedback: `placeholderData` keeps the
                    previous range's bars on screen while the new ones load
                    (intraday hits yfinance live → can take seconds). Without
                    a cue the click looks ignored. Show a small badge while a
                    refetch runs over stale/placeholder data. */}
                {detail.isFetching && detail.isPlaceholderData && (
                  <div className="absolute top-2 right-2 z-20 flex items-center gap-1.5 rounded-md border bg-card/90 backdrop-blur-sm px-2 py-1 text-xs text-muted-foreground shadow-sm pointer-events-none">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                    Aggiornamento…
                  </div>
                )}
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
                  signalMarkers={signalOverlay.markers}
                  signalsByTime={signalOverlay.byTime}
                  earningsMarkers={earningsMarkers}
                  chartType={chartType}
                  benchmarkLine={benchmarkLine}
                  benchmarkLabel={benchmarkLabel}
                  compareLine={compareLine}
                  compareLabel={compareTicker || undefined}
                  chartApiRef={chartApiRef}
                  exchangeTz={exchangeTimezone(ticker)}
                  eraseMode={mode === "erase"}
                  onDeleteHorizontal={drawings.removeHorizontal}
                  onDeleteTrend={drawings.removeTrend}
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
