import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { scores } from "@/api/scores";
import type { StockScore } from "@/api/types";

/** Result returned by `useStockScore`. Mirrors the TanStack Query state shape
 *  but adds an explicit `noScoreYet` flag so consumers don't have to inspect
 *  the error object to distinguish "score not computed yet" (a normal state
 *  the UI handles with a friendly placeholder) from "real network error". */
export interface UseStockScoreResult {
  data: StockScore | null;
  isLoading: boolean;
  isError: boolean;
  /** True when the backend returned 404 — either ticker unknown or score not
   *  yet computed. Both render the same placeholder; the API distinguishes
   *  them by detail message but the UI treats them as one empty state. */
  noScoreYet: boolean;
  refetch: () => void;
}

export function useStockScore(ticker: string | undefined): UseStockScoreResult {
  const query = useQuery<StockScore, ApiError>({
    queryKey: ["stock-score", ticker],
    queryFn: () => scores.forStock(ticker!),
    enabled: !!ticker,
    // Score recomputes after every scan (~hourly cadence). 1h client cache
    // avoids re-fetching on tab switches without serving stale-stale data.
    staleTime: 60 * 60_000,
    retry: (failureCount, error) => {
      // Don't retry on 404 — it means "not yet computed", a normal state.
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 1;
    },
  });

  const noScoreYet =
    query.isError &&
    query.error instanceof ApiError &&
    query.error.status === 404;

  return {
    data: query.data ?? null,
    isLoading: query.isLoading,
    // 404 is not surfaced as an error — UI gets `noScoreYet` instead.
    isError: query.isError && !noScoreYet,
    noScoreYet,
    refetch: () => query.refetch(),
  };
}
