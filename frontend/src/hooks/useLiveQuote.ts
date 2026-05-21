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
 * Batch variant — returns live quotes for N tickers. Useful for the
 * dashboard where we want live prices for a WIDE pool of candidate
 * movers without spawning N React-Query subscriptions.
 *
 * Chunking (May 2026): the backend caps each request at 50 tickers
 * (rate-limit safety). To poll a broader candidate pool — so that an
 * intraday mover OUTSIDE the EOD top set can actually surface when we
 * re-rank on live prices — we split `tickers` into <=50 chunks and
 * fire them in PARALLEL (Promise.all), then merge. The backend
 * parallelises within each chunk too, so even a ~120-name pool
 * resolves in ~1-2s. Without this the live poll only ever saw the
 * handful of already-displayed names, so the "top movers" were
 * effectively frozen to the EOD ranking.
 */
const _BATCH_SIZE = 50;

export function useLiveQuotes(tickers: string[], enabled: boolean = true) {
  const sorted = [...tickers].sort();
  const key = sorted.join(",");
  return useQuery({
    queryKey: ["live-quotes-batch", key],
    queryFn: async () => {
      // Split into <=50-ticker chunks, fetch in parallel, merge.
      const chunks: string[][] = [];
      for (let i = 0; i < sorted.length; i += _BATCH_SIZE) {
        chunks.push(sorted.slice(i, i + _BATCH_SIZE));
      }
      const results = await Promise.all(
        chunks.map((c) =>
          api<{ quotes: LiveQuote[] }>(
            `/api/stocks/quotes?tickers=${encodeURIComponent(c.join(","))}`,
          ),
        ),
      );
      return { quotes: results.flatMap((r) => r.quotes) };
    },
    enabled: enabled && tickers.length > 0,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}
