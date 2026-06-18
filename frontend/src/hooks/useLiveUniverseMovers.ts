import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

export interface LiveMover {
  ticker: string;
  name: string | null;
  change_pct: number;
  price: number | null;
}
export interface LiveMoversResponse {
  gainers: LiveMover[];
  losers: LiveMover[];
  /** How many universe tickers currently have a fresh live quote staged. */
  swept: number;
}

/**
 * Universe-wide live top movers from the backend rotating sweep
 * (live_universe_sweep_service). The dashboard merges these tickers INTO its
 * 1G candidate pool so a genuine intraday mover that wasn't an EOD mover still
 * surfaces. Polled at 60s (the sweep itself rotates every ~75s, so faster
 * client polling buys nothing); paused in the background tab.
 */
export function useLiveUniverseMovers(enabled: boolean = true) {
  return useQuery({
    queryKey: ["live-universe-movers"],
    queryFn: () => api<LiveMoversResponse>("/api/dashboard/live-movers"),
    enabled,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    staleTime: 30_000,
  });
}
