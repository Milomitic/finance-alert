import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { LiveQuote } from "@/api/types";

// Poll fast (15s) while a market can move; back off (60s) once we're CONFIDENT
// it's closed. yfinance's marketState is the signal: only these explicit
// closed-ish states trigger the back-off — an unknown/null state stays fast so
// an asset that doesn't report a state is never under-polled during the day.
const FAST_MS = 15_000;
const CLOSED_MS = 60_000;
const CLOSED_STATES = new Set(["CLOSED", "PREPRE", "POSTPOST"]);

function isClosed(state: string | null | undefined): boolean {
  return state != null && CLOSED_STATES.has(state);
}

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
    refetchInterval: (query) =>
      isClosed(query.state.data?.market_state) ? CLOSED_MS : FAST_MS,
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
    // Back off only when EVERY quote in the batch is confidently closed (e.g.
    // overnight/weekend). If any single market is open, keep the fast cadence.
    refetchInterval: (query) => {
      const quotes = query.state.data?.quotes ?? [];
      if (quotes.length === 0) return FAST_MS;
      return quotes.every((q) => isClosed(q.market_state)) ? CLOSED_MS : FAST_MS;
    },
    refetchIntervalInBackground: false,
    staleTime: 5_000,
    // The key embeds the ticker pool, and the 60s universe sweep can shift the
    // pool membership → new key. Without these, every shift flashed a loading
    // gap (no data under the new key) and stranded the old entry in cache for
    // the default 5min gcTime. placeholderData carries the previous batch over
    // (most tickers overlap); the short gcTime collects the orphaned keys.
    placeholderData: (prev) => prev,
    gcTime: 60_000,
  });
}
