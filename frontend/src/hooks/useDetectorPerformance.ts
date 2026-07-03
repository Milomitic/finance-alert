import { useQuery } from "@tanstack/react-query";

import { fetchDetectorPerformance } from "@/api/platformHealth";

/** Detector × regime × tono × Forza performance cube over the matured
 *  `signal_outcomes` warehouse. Slow-moving (grows a handful of rows per
 *  scan), so cache generously; `enabled` lets the collapsible Settings panel
 *  defer the fetch until first opened. */
export function useDetectorPerformance(enabled = true) {
  return useQuery({
    queryKey: ["signals", "detector-performance"],
    queryFn: fetchDetectorPerformance,
    enabled,
    staleTime: 30 * 60_000, // 30m — outcomes mature only at scan end
    gcTime: 60 * 60_000,
  });
}
