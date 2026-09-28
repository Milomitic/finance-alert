import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

export interface TimeframeKpis {
  timeframe: string;
  bars: number;
  last_close: number | null;
  rsi: number | null;
  rsi_tone: "oversold" | "overbought" | "neutral";
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  ema20_above: boolean | null;
  ema50_above: boolean | null;
  ema200_above: boolean | null;
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

function suffisso(timeframes: readonly string[] | undefined): string {
  return timeframes && timeframes.length > 0
    ? `?timeframes=${encodeURIComponent(timeframes.join(","))}`
    : "";
}

/** Per-stock multi-timeframe KPIs. Catalog-resolved; daily timeframes
 *  are DB-fast, intraday hits yfinance + 5min cache. ~5min staleTime
 *  matches the backend's intraday cache so we don't refetch faster
 *  than the data could change.
 *
 *  `timeframes` (FA-110) chiede solo quelli: la scheda chiede i giornalieri e
 *  l'intraday separatamente, cosi' i primi arrivano dal database senza
 *  aspettare Yahoo. Senza, il server li calcola tutti. */
export function useStockMultiTfKpis(ticker: string, timeframes?: readonly string[]) {
  return useQuery({
    queryKey: ["multi-tf-kpis", "stock", ticker, timeframes ?? "tutti"],
    queryFn: ({ signal }) =>
      api<MultiTfKpis>(
        `/api/stocks/${encodeURIComponent(ticker)}/multi-tf-kpis${suffisso(timeframes)}`,
        { signal },
      ),
    staleTime: 5 * 60_000,
    enabled: !!ticker,
  });
}

/** Per-market-symbol multi-TF KPIs (^GSPC, BTC-USD, GC=F, …). */
export function useMarketMultiTfKpis(symbol: string, timeframes?: readonly string[]) {
  return useQuery({
    queryKey: ["multi-tf-kpis", "market", symbol, timeframes ?? "tutti"],
    queryFn: ({ signal }) =>
      api<MultiTfKpis>(
        `/api/markets/${encodeURIComponent(symbol)}/multi-tf-kpis${suffisso(timeframes)}`,
        { signal },
      ),
    staleTime: 5 * 60_000,
    enabled: !!symbol,
  });
}
