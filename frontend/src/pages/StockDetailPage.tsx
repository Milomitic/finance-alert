import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import type { PriceAlert } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useCreatePriceAlert, useStockPriceAlerts } from "@/hooks/useStockPriceAlerts";
import { useStockDetail } from "@/hooks/useStockDetail";
import { useStockDrawings } from "@/hooks/useStockDrawings";
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
      <StockHeader stock={d.stock} kpis={d.kpis} effectiveRules={d.effective_rules} />

      {/* Three side-by-side cards: Fundamentals | Valuation | News.
          Fixed row height → all 3 cards share the same height; each one's
          internal content scrolls if needed. The Fundamentals card uses
          tabs (Annuali / Trimestrali / Earnings) to fit in the same box. */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 lg:h-[400px]">
        <FundamentalsCard ticker={ticker} />
        <MicroDataCard ticker={ticker} />
        <NewsCard ticker={ticker} />
      </div>

      {/* Insiders & Analyst stays full-width below — its tables (analyst bars
          + insider list) are wide and would get cramped in a third of a row. */}
      <InsidersAnalystCard ticker={ticker} />

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
                <span className="text-[11px] uppercase tracking-wider font-bold text-muted-foreground shrink-0">
                  Indicatori
                </span>
                <div className="h-4 w-px bg-border" />
                <IndicatorToggles state={indicators} onChange={onIndicatorChange} />
              </div>
            </div>

            {/* Price chart — resizable; defaults to 460px */}
            {d.ohlcv.length < 2 ? (
              <div className="h-[460px] flex items-center justify-center text-sm text-muted-foreground border border-border/50 rounded-md">
                Dati insufficienti per il chart
              </div>
            ) : (
              <ResizableSection defaultHeight={460} minHeight={240} label="Price">
                <PriceChart
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
                />
              </ResizableSection>
            )}

            {/* RSI sub-panel — togglable + resizable */}
            {indicators.rsi.visible && d.indicators.rsi14.length > 0 && (
              <div className="mt-3">
                <ResizableSection defaultHeight={140} minHeight={80} label="RSI(14)">
                  <RsiPanel rsi14={d.indicators.rsi14} color={indicators.rsi.color} width={indicators.rsi.width} />
                </ResizableSection>
              </div>
            )}

            {/* MACD sub-panel — togglable + resizable */}
            {indicators.macd.visible && hasMacd && (
              <div className="mt-3">
                <ResizableSection defaultHeight={160} minHeight={80} label="MACD(12,26,9)">
                  <MacdPanel
                    line={d.indicators.macd_line ?? []}
                    signal={d.indicators.macd_signal ?? []}
                    hist={d.indicators.macd_hist ?? []}
                    color={indicators.macd.color}
                    width={indicators.macd.width}
                  />
                </ResizableSection>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-3">
          <TechnicalKpiCard kpis={d.kpis} indicators={d.indicators} />
          <PriceAlertsCard ticker={ticker} />
          <StockAlertsHistoryCard alerts={d.alerts_history} />
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
