import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  /** Force a backend recomputation. Hits POST /score/recompute which forces
   *  a fundamentals refetch + compute_score + persist, then writes the
   *  fresh result into the React-Query cache so the UI updates without a
   *  follow-up GET round-trip. */
  recompute: () => void;
  /** True while the recompute mutation is in-flight. Bound to the refresh
   *  button's `disabled` + spinner state. */
  isRecomputing: boolean;
}

export function useStockScore(ticker: string | undefined): UseStockScoreResult {
  const qc = useQueryClient();
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

  // POST recompute mutation. On success, write the returned score directly
  // into the cache so the UI flips to the fresh value without a separate
  // GET. We still invalidate to mark the entry "fresh enough" so any other
  // subscribers (e.g. a hypothetical second StockScoreCard for the same
  // ticker) re-render too.
  const recomputeMutation = useMutation<StockScore, ApiError, void>({
    mutationFn: () => scores.recomputeForStock(ticker!),
    onSuccess: (fresh) => {
      qc.setQueryData(["stock-score", ticker], fresh);
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
    recompute: () => recomputeMutation.mutate(),
    isRecomputing: recomputeMutation.isPending,
  };
}
