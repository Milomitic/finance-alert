import { useQuery } from "@tanstack/react-query";

import { dashboard } from "@/api/dashboard";

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => dashboard.summary(),
    // Scan-derived, like market-summary: useScanStatus invalidates ["dashboard"]
    // on scan completion. Foreground-only safety poll + refetch on tab focus
    // instead of a 30s background poll on every page.
    refetchInterval: 5 * 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  });
}
