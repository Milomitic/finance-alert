import { useQuery } from "@tanstack/react-query";

import { market } from "@/api/market";

export function useMarketSummary() {
  return useQuery({
    queryKey: ["dashboard", "market-summary"],
    queryFn: () => market.summary(),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    staleTime: 10_000,
  });
}
