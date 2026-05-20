import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { dashboard } from "@/api/dashboard";

const KEY = ["dashboard", "premarket-movers"] as const;

/** Polls the cached US pre-market movers. While a refresh is in flight
 *  it polls fast (every 2s) so the card's % progress moves smoothly;
 *  otherwise every 30s (the scheduler refreshes the cache during the
 *  pre-market window — no need to hammer it). Background polling is off:
 *  this card is only relevant when the user is looking at the
 *  dashboard with the US market closed. */
export function usePremarketMovers() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => dashboard.premarketMovers(),
    refetchInterval: (q) =>
      q.state.data?.refreshing ? 2_000 : 30_000,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}

/** Fires the on-demand recompute (the card's manual refresh button).
 *  On success we immediately invalidate so the next poll picks up
 *  `refreshing: true` and the fast 2s cadence kicks in. */
export function useRefreshPremarketMovers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => dashboard.refreshPremarketMovers(),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
