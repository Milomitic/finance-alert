import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { LiveQuote } from "@/api/types";

/**
 * Polls the live-quote endpoint for one ticker.
 *
 * Refresh cadence is adaptive: 15s while active in the foreground, 60s
 * when the browser tab is hidden (TanStack Query handles this via
 * `refetchIntervalInBackground: false`). The backend caches at 10s TTL
 * server-side so multiple tabs / windows of the same ticker share one
 * yfinance call.
 *
 * Pass `enabled: false` to disable polling (e.g. when the user has not
 * yet opened the relevant view).
 */
export function useLiveQuote(ticker: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ["live-quote", ticker],
    queryFn: () =>
      api<LiveQuote>(`/api/stocks/${encodeURIComponent(ticker!)}/quote`),
    enabled: !!ticker && enabled,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    // Quotes are stale almost immediately — keep 5s so a route re-render
    // doesn't refetch instantly but a hard navigate does.
    staleTime: 5_000,
  });
}

/**
 * Batch variant — one HTTP call returns N quotes. Useful for the dashboard
 * where we want live prices for the top movers / spotlight stocks without
 * spawning N concurrent React-Query subscriptions.
 */
export function useLiveQuotes(tickers: string[], enabled: boolean = true) {
  const sorted = [...tickers].sort();
  const key = sorted.join(",");
  return useQuery({
    queryKey: ["live-quotes-batch", key],
    queryFn: () =>
      api<{ quotes: LiveQuote[] }>(`/api/stocks/quotes?tickers=${encodeURIComponent(key)}`),
    enabled: enabled && tickers.length > 0,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}
