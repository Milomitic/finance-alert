import { useQuery } from "@tanstack/react-query";

import { scores, type TopPicksParams } from "@/api/scores";

export function useTopPicks(opts: TopPicksParams = {}) {
  return useQuery({
    queryKey: ["top-picks", opts],
    queryFn: () => scores.top(opts),
    // Top-picks list is cheap to compute server-side and recomputes on each
    // scan. 5-minute client cache balances freshness vs not pinging on every
    // tab switch back to the dashboard.
    staleTime: 5 * 60_000,
  });
}
