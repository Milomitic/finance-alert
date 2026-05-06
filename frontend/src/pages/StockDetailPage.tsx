import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import type { PriceAlert } from "@/api/types";
import { MultiTimeframeKpisCard } from "@/components/MultiTimeframeKpisCard";
import { Card, CardContent } from "@/components/ui/card";
import { useChartSync } from "@/hooks/useChartSync";
import { useCreatePriceAlert, useStockPriceAlerts } from "@/hooks/useStockPriceAlerts";
import { useStockDetail } from "@/hooks/useStockDetail";
import { useStockDrawings } from "@/hooks/useStockDrawings";
import { AnalystTargetCard } from "@/components/stock/AnalystTargetCard";
import { CompanyOverviewCard } from "@/components/stock/CompanyOverviewCard";
import { DrawingToolbar, type DrawingMode } from "@/components/stock/DrawingToolbar";
import { FundamentalsCard } from "@/components/stock/FundamentalsCard";
import { InsidersAnalystCard } from "@/components/stock/InsidersAnalystCard";
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
import { StockScoreCard } from "@/components/stock/StockScoreCard";
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

  const [indicators, setIndicators] = useState<IndicatorState>(DEFAULT_INDICATOR_STATE);
  const [mode, setMode] = useState<DrawingMode>("none");
  const [pendingPrice, setPendingPrice] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  // Chart-sync orchestrator: PriceChart + RsiPanel + MacdPanel each
  // register with this on mount, the hook then forwards every pan/zoom
  // event from any one chart to the others so the time axis stays
  // anchored across the stack. Stable across renders — safe to pass as
  // a prop without re-mounting the children.
  const registerChart = useChartSync();

  const onIndicatorChange = (key: IndicatorKey, next: IndicatorStyle) =>
    setIndicators((prev) => ({ ...prev, [key]: next }));

  const handleChartClick = (price: number) => {
    if (mode === "alert") {
      setPendingPrice(price);
      setDialogOpen(true);
      setMode("none");
    } else if (mode === "hline") {
      drawings.addHorizontal(Math.round(price * 100) / 100);
      setMode("none");
    }
  };

  if (detail.isLoading) {
    return (
      <div className="space-y-3">
        <Card><CardContent className="p-4 h-[100px] animate-pulse bg-muted/40" /></Card>
        <div className="grid lg:grid-cols-[1fr_320px] gap-3">
          <Card><CardContent className="p-4 h-[600px] animate-pulse bg-muted/40" /></Card>
          <div className="space-y-3">
            {[0,1,2,3,4].map((i) =>
              <Card key={i}><CardContent className="p-4 h-[100px] animate-pulse bg-muted/40" /></Card>
            )}
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
  const priceAlerts: PriceAlert[] = priceAlertsQuery.data ?? [];
  const lastClose = d.kpis.last_close ?? 0;

  const hasMacd = (d.indicators.macd_line?.length ?? 0) > 0;

  return (
    <div className="space-y-3">
      {/* Top hero — StockHeader spans full width now. The Analyst card was
          relocated to the data-row below (4th column) so the hero stays
          purely identity/price-trend focused. */}
      <StockHeader
        stock={d.stock}
        kpis={d.kpis}
        ohlcv={d.ohlcv}
        effectiveRules={d.effective_rules}
      />

      {/* Company overview (left, 67%) + Alert storici (right, 33%).
          Equal-height row (`items-stretch`, the grid default): the
          alerts card fills the height set by the company-profile prose
          and scrolls internally when there are more rows than fit.
          The profile is the page's lead content and dictates the row
          height; the alerts card adapts. Stacks vertically below `lg`. */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3">
        <CompanyOverviewCard ticker={ticker} stock={d.stock} />
        <StockAlertsHistoryCard alerts={d.alerts_history} />
      </div>

      {/* Multi-timeframe KPI comparison — same indicator suite (RSI 14,
          BB 20, SMA 20/50/200, MACD 12/26/9) computed across 30m / 1h
          / 1d / 1w / 1m / all. Lets the user spot short-vs-long-term
          disagreements at a glance. */}
      <MultiTimeframeKpisCard ticker={ticker} kind="stock" />

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
        <FundamentalsCard ticker={ticker} />
        <MicroDataCard ticker={ticker} stock={d.stock} kpis={d.kpis} />
        <NewsCard ticker={ticker} />
        <AnalystTargetCard ticker={ticker} />
      </div>

      {/* The dedicated Alerts + Insiders row that used to live here was
          decomposed: alerts moved next to the company profile (above),
          insiders moved into the right-hand sidebar (below) so the
          chart can dominate the vertical real estate that the row
          used to consume. */}

      <div className="grid lg:grid-cols-[1fr_400px] gap-3">
        <Card>
          <CardContent className="p-4">
            {/* Toolbar: range on the left, indicators row, drawing tools on the right.
                Each row breaks independently when the card narrows. */}
            <div className="space-y-2 mb-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <RangeSelector
                  value={range}
                  onChange={(r) => setSearchParams({ range: r })}
                />
                <DrawingToolbar
                  mode={mode}
                  onSetMode={setMode}
                  onClearAll={drawings.clearAll}
                />
              </div>
              <div className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-muted/30 border border-border/50">
                <span className="text-[13px] uppercase tracking-wider font-bold text-muted-foreground shrink-0">
                  Indicatori
                </span>
                <div className="h-4 w-px bg-border" />
                <IndicatorToggles
                  state={indicators}
                  onChange={onIndicatorChange}
                  periods={d.indicators.periods}
                />
              </div>
            </div>

            {/* Price chart — resizable; defaults to 460px */}
            {d.ohlcv.length < 2 ? (
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
                  ohlcv={d.ohlcv}
                  indicators={d.indicators}
                  styles={{
                    sma20: indicators.sma20,
                    sma50: indicators.sma50,
                    sma200: indicators.sma200,
                    bb: indicators.bb,
                  }}
                  priceAlerts={priceAlerts}
                  horizontalDrawings={drawings.drawings.horizontal}
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
                    rsi14={d.indicators.rsi14}
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
                    line={d.indicators.macd_line ?? []}
                    signal={d.indicators.macd_signal ?? []}
                    hist={d.indicators.macd_hist ?? []}
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
          <StockScoreCard ticker={ticker} />
          <TechnicalKpiCard kpis={d.kpis} indicators={d.indicators} />
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
