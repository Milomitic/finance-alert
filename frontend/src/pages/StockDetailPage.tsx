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
import { IndicatorToggles } from "@/components/stock/IndicatorToggles";
import { NewsCard } from "@/components/stock/NewsCard";
import { PriceAlertDialog } from "@/components/stock/PriceAlertDialog";
import { PriceAlertsCard } from "@/components/stock/PriceAlertsCard";
import { PriceChart } from "@/components/stock/PriceChart";
import { RangeSelector } from "@/components/stock/RangeSelector";
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

  const [showSma50, setShowSma50] = useState(true);
  const [showSma200, setShowSma200] = useState(true);
  const [mode, setMode] = useState<DrawingMode>("none");
  const [pendingPrice, setPendingPrice] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const handleChartClick = (price: number) => {
    if (mode === "alert") {
      setPendingPrice(price);
      setDialogOpen(true);
      setMode("none");
    } else if (mode === "hline") {
      drawings.addHorizontal(Math.round(price * 100) / 100);
      setMode("none");
    }
    // mode === "trend" is deferred — no-op for now
  };

  if (detail.isLoading) {
    return (
      <div className="space-y-3">
        <Card><CardContent className="p-4 h-[80px] animate-pulse bg-muted/40" /></Card>
        <div className="grid lg:grid-cols-[1fr_320px] gap-3">
          <Card><CardContent className="p-4 h-[540px] animate-pulse bg-muted/40" /></Card>
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

  return (
    <div className="space-y-3">
      <StockHeader stock={d.stock} kpis={d.kpis} />

      <div className="grid lg:grid-cols-[1fr_320px] gap-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <RangeSelector
                value={range}
                onChange={(r) => setSearchParams({ range: r })}
              />
              <div className="flex items-center gap-3">
                <IndicatorToggles
                  showSma50={showSma50}
                  showSma200={showSma200}
                  onToggle={(k, v) => k === "sma50" ? setShowSma50(v) : setShowSma200(v)}
                />
                <DrawingToolbar
                  mode={mode}
                  onSetMode={setMode}
                  onClearAll={drawings.clearAll}
                />
              </div>
            </div>
            {d.ohlcv.length < 2 ? (
              <div className="h-[420px] flex items-center justify-center text-sm text-muted-foreground">
                Dati insufficienti per il chart
              </div>
            ) : (
              <PriceChart
                ohlcv={d.ohlcv}
                indicators={d.indicators}
                showSma50={showSma50}
                showSma200={showSma200}
                priceAlerts={priceAlerts}
                horizontalDrawings={drawings.drawings.horizontal}
                onChartClick={handleChartClick}
              />
            )}
            {d.indicators.rsi14.length > 0 && (
              <div className="mt-2">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                  RSI(14)
                </div>
                <RsiPanel rsi14={d.indicators.rsi14} />
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-3">
          <TechnicalKpiCard kpis={d.kpis} indicators={d.indicators} />
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
