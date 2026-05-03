import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import type { PriceAlert } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useCreatePriceAlert, useStockPriceAlerts } from "@/hooks/useStockPriceAlerts";
import { useStockDetail } from "@/hooks/useStockDetail";
import { useStockDrawings } from "@/hooks/useStockDrawings";
import { DrawingToolbar, type DrawingMode } from "@/components/stock/DrawingToolbar";
import { EffectiveRulesCard } from "@/components/stock/EffectiveRulesCard";
import { FundamentalsCard } from "@/components/stock/FundamentalsCard";
import {
  IndicatorToggles, type IndicatorKey, type IndicatorState,
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

const DEFAULT_INDICATORS: IndicatorState = {
  sma20: false,
  sma50: true,
  sma200: true,
  bb: false,
  rsi: true,
  macd: false,
};

export default function StockDetailPage() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const range = searchParams.get("range") ?? "1y";

  const detail = useStockDetail(ticker, range);
  const priceAlertsQuery = useStockPriceAlerts(ticker);
  const createPa = useCreatePriceAlert(ticker);
  const drawings = useStockDrawings(ticker);

  const [indicators, setIndicators] = useState<IndicatorState>(DEFAULT_INDICATORS);
  const [mode, setMode] = useState<DrawingMode>("none");
  const [pendingPrice, setPendingPrice] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const onToggle = (key: IndicatorKey, value: boolean) =>
    setIndicators((prev) => ({ ...prev, [key]: value }));

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
      <StockHeader stock={d.stock} kpis={d.kpis} />

      <div className="grid lg:grid-cols-[1fr_320px] gap-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <RangeSelector
                value={range}
                onChange={(r) => setSearchParams({ range: r })}
              />
              <div className="flex items-center gap-3 flex-wrap">
                <IndicatorToggles state={indicators} onToggle={onToggle} />
                <DrawingToolbar
                  mode={mode}
                  onSetMode={setMode}
                  onClearAll={drawings.clearAll}
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
                <PriceChart
                  ohlcv={d.ohlcv}
                  indicators={d.indicators}
                  showSma20={indicators.sma20}
                  showSma50={indicators.sma50}
                  showSma200={indicators.sma200}
                  showBb={indicators.bb}
                  priceAlerts={priceAlerts}
                  horizontalDrawings={drawings.drawings.horizontal}
                  onChartClick={handleChartClick}
                />
              </ResizableSection>
            )}

            {/* RSI sub-panel — togglable + resizable */}
            {indicators.rsi && d.indicators.rsi14.length > 0 && (
              <div className="mt-3">
                <ResizableSection defaultHeight={140} minHeight={80} label="RSI(14)">
                  <RsiPanel rsi14={d.indicators.rsi14} />
                </ResizableSection>
              </div>
            )}

            {/* MACD sub-panel — togglable + resizable */}
            {indicators.macd && hasMacd && (
              <div className="mt-3">
                <ResizableSection defaultHeight={160} minHeight={80} label="MACD(12,26,9)">
                  <MacdPanel
                    line={d.indicators.macd_line ?? []}
                    signal={d.indicators.macd_signal ?? []}
                    hist={d.indicators.macd_hist ?? []}
                  />
                </ResizableSection>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-3">
          <TechnicalKpiCard kpis={d.kpis} indicators={d.indicators} />
          <FundamentalsCard ticker={ticker} />
          <PriceAlertsCard ticker={ticker} />
          <StockAlertsHistoryCard alerts={d.alerts_history} />
          <EffectiveRulesCard rules={d.effective_rules} />
          <NewsCard ticker={ticker} />
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
