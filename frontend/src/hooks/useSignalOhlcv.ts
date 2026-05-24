import { useQuery } from "@tanstack/react-query";

import { stocks } from "@/api/stocks";

/** Lazy daily-OHLCV window for the annotated signal chart. `enabled` gates the
 *  fetch so it only fires when a signal detail popup is open. */
export function useSignalOhlcv(ticker: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["signal-ohlcv", ticker],
    queryFn: () => stocks.ohlcv(ticker as string, 260),
    enabled: enabled && !!ticker,
    staleTime: 5 * 60_000,
  });
}
