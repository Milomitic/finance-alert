import { useQuery } from "@tanstack/react-query";

import { fetchSignalDrift, type SignalDriftRow } from "@/api/platformHealth";

/** Per-detector drift verdicts (recent matured hit-rate vs calibrated base).
 *  Detector-level + slow-moving, so cache for a while and share across popups.
 *  Returns a Map keyed by detector for O(1) lookup in the signal detail. */
export function useSignalDrift() {
  return useQuery({
    queryKey: ["signals", "drift"],
    queryFn: async () => {
      const { detectors } = await fetchSignalDrift();
      const byDetector = new Map<string, SignalDriftRow>();
      for (const row of detectors) byDetector.set(row.detector, row);
      return byDetector;
    },
    staleTime: 30 * 60_000, // 30m — drift moves slowly (matured-alert window)
    gcTime: 60 * 60_000,
  });
}
