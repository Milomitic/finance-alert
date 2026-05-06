import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

export interface MarketDetailBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface MarketDetailQuote {
  price: number | null;
  prev_close: number | null;
  change_abs: number | null;
  change_pct: number | null;
  market_state: string | null;
  currency: string | null;
  error: string | null;
}

export interface MarketDetail {
  symbol: string;
  name: string;
  category: "index" | "commodity" | "crypto";
  flag: string | null;
  range_key: string;
  last_close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  high_window: number | null;
  low_window: number | null;
  high_52w: number | null;
  low_52w: number | null;
  bars: MarketDetailBar[];
  quote: MarketDetailQuote | null;
}

/** Fetch detail for a non-stock instrument (index / commodity /
 *  crypto) listed in the dashboard's LiveAssetsPanel. The 60s
 *  staleTime matches the backend's 15-min OHLCV cache + 10s quote
 *  cache: bars don't move intraday at 1d resolution, the live
 *  quote ticks separately via `useLiveQuote` if the page wants it. */
export function useMarketDetail(symbol: string, range: string = "1y") {
  return useQuery({
    queryKey: ["market-detail", symbol, range],
    queryFn: () =>
      api<MarketDetail>(
        `/api/markets/${encodeURIComponent(symbol)}/detail?range=${range}`,
      ),
    staleTime: 60_000,
    enabled: !!symbol,
  });
}
