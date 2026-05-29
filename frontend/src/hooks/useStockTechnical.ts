import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { scores } from "@/api/scores";
import type { TechnicalScoreDetail } from "@/api/types";

/** Single-stock continuous technical score. 404 (noScoreYet) when not yet
 *  computed -- rendered as a friendly placeholder, like useStockScore. */
export function useStockTechnical(ticker: string | undefined) {
  const query = useQuery<TechnicalScoreDetail, ApiError>({
    queryKey: ["stock-technical", ticker],
    queryFn: () => scores.technicalForStock(ticker!),
    enabled: !!ticker,
    staleTime: 60 * 60_000,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 1;
    },
  });
  const noScoreYet =
    query.isError && query.error instanceof ApiError && query.error.status === 404;
  return {
    data: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError && !noScoreYet,
    noScoreYet,
    /** ms timestamp of the last cache write — drives the "aggiornato …" label. */
    dataUpdatedAt: query.dataUpdatedAt,
  };
}
