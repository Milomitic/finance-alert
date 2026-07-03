import { useQuery } from "@tanstack/react-query";

import { market } from "@/api/market";

export function useMarketSummary() {
  return useQuery({
    queryKey: ["dashboard", "market-summary"],
    queryFn: () => market.summary(),
    // This payload (~264KB) is scan-derived — it only changes when a scan
    // completes. useScanStatus invalidates ["dashboard"] on that transition, so
    // the old 30s background poll on every page (incl. hidden tabs) was pure
    // waste. Keep a long foreground-only safety net + refetch on tab focus.
    refetchInterval: 5 * 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  });
}
