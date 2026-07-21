import { useQuery, type QueryKey } from "@tanstack/react-query";

import { stocks } from "@/api/stocks";

/**
 * Stock-detail query. Two trade-offs encoded here:
 *
 * 1. `placeholderData` keeps the previous response visible only when
 *    the TICKER is unchanged. Without that scoping (the old version
 *    used a no-op `(prev) => prev`), navigating from /stocks/FOO to
 *    /stocks/BAR would briefly show FOO's chart bars under BAR's
 *    header — and if the network call was slow, the user could
 *    snapshot a chart with wildly out-of-range Y-axis (FOO at $400
 *    while BAR really trades at $4). The ticker-scoped placeholder
 *    keeps the smooth "different timeframe of the same stock" UX
 *    while killing the cross-ticker bleed.
 *
 * 2. `staleTime: 30s` matches the dashboard polling cadence — the
 *    user can switch tabs and come back within half a minute
 *    without paying a refetch.
 */
export function useStockDetail(ticker: string, range: string = "1y", enabled = true) {
  return useQuery({
    enabled: enabled && !!ticker,
    queryKey: ["stock-detail", ticker, range],
    queryFn: () => stocks.detail(ticker, range),
    placeholderData: (prev, prevQuery) => {
      // Only reuse the previous query result when its ticker matches
      // the new one (i.e. only the `range` changed). Different ticker
      // → return undefined so the page renders its loading skeleton
      // instead of bleeding the other stock's bars onto this chart.
      const prevKey = prevQuery?.queryKey as QueryKey | undefined;
      const prevTicker =
        Array.isArray(prevKey) && prevKey.length >= 2 ? prevKey[1] : undefined;
      return prevTicker === ticker ? prev : undefined;
    },
    staleTime: 30_000,
  });
}
