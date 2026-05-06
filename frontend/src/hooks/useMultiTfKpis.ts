import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

export interface TimeframeKpis {
  timeframe: string;
  bars: number;
  last_close: number | null;
  rsi: number | null;
  rsi_tone: "oversold" | "overbought" | "neutral";
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  sma20_above: boolean | null;
  sma50_above: boolean | null;
  sma200_above: boolean | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  bb_position: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  macd_tone: "bullish" | "bearish" | "neutral";
  composite_score: number;
  composite_label:
    | "very_bullish"
    | "bullish"
    | "neutral"
    | "bearish"
    | "very_bearish";
}

export interface MultiTfKpis {
  ticker: string;
  items: TimeframeKpis[];
}

/** Per-stock multi-timeframe KPIs. Catalog-resolved; daily timeframes
 *  are DB-fast, intraday hits yfinance + 5min cache. ~5min staleTime
 *  matches the backend's intraday cache so we don't refetch faster
 *  than the data could change. */
export function useStockMultiTfKpis(ticker: string) {
  return useQuery({
    queryKey: ["multi-tf-kpis", "stock", ticker],
    queryFn: () =>
      api<MultiTfKpis>(
        `/api/stocks/${encodeURIComponent(ticker)}/multi-tf-kpis`,
      ),
    staleTime: 5 * 60_000,
    enabled: !!ticker,
  });
}

/** Per-market-symbol multi-TF KPIs (^GSPC, BTC-USD, GC=F, …). */
export function useMarketMultiTfKpis(symbol: string) {
  return useQuery({
    queryKey: ["multi-tf-kpis", "market", symbol],
    queryFn: () =>
      api<MultiTfKpis>(
        `/api/markets/${encodeURIComponent(symbol)}/multi-tf-kpis`,
      ),
    staleTime: 5 * 60_000,
    enabled: !!symbol,
  });
}
