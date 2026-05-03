import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Fundamentals } from "@/api/types";

export function useStockFundamentals(ticker: string | undefined) {
  return useQuery({
    queryKey: ["stocks", ticker, "fundamentals"],
    queryFn: () =>
      api<Fundamentals>(`/api/stocks/${encodeURIComponent(ticker!)}/fundamentals`),
    enabled: !!ticker,
    // Backend caches 24h; client caches 1h to avoid pinging on every tab switch
    staleTime: 60 * 60_000,
  });
}
