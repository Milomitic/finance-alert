import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import type { PriceAlert } from "@/api/types";
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
import { PriceAlertsCard } from "@/components/stock/PriceAlertsCard";
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
  const range = searchParams.get("range") ?? "1y";

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

      {/* Company overview — short business summary + anagrafica.
          Positioned prominently right under the price hero so the user
          gets "what does this company do" before diving into numbers.
          The card hides itself when yfinance has no profile data
          (sparse small caps / foreign listings), so it doesn't always
          take up vertical space. */}
      <CompanyOverviewCard ticker={ticker} stock={d.stock} />

      {/* Four side-by-side cards: Fundamentals | Valuation+KPIs | News | Analyst.
          Weighted columns `[1.5fr_1fr_1fr_1fr]` give Fundamentals ~33% (it has
          a 7-column earnings table that needs the breathing room) and the
          other three each ~22%. Per FundamentalsCard's no-scroll constraint,
          it sets the row floor; the other three cards (Valuation, News,
          Analyst) all have internal scrollers / max-h caps that absorb
          extra vertical space gracefully. */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr_1fr_1fr] gap-3">
        <FundamentalsCard ticker={ticker} />
        <MicroDataCard ticker={ticker} stock={d.stock} kpis={d.kpis} />
        <NewsCard ticker={ticker} />
        <AnalystTargetCard ticker={ticker} />
      </div>

      {/* Alerts history + Insiders/Analyst side-by-side. Equal-width so the
          two list-style cards balance visually; `items-start` lets each size
          to its content (alerts can be very short, insiders can be long).
          Stacks vertically on narrow viewports. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start">
        <StockAlertsHistoryCard alerts={d.alerts_history} />
        <InsidersAnalystCard ticker={ticker} />
      </div>

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
          <PriceAlertsCard ticker={ticker} />
          {/* StockAlertsHistoryCard moved to a full-width prominent row above
              (right after the 3-card row). Kept the sidebar slot empty rather
              than rendering twice. */}
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
