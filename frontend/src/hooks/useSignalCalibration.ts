import { useQuery } from "@tanstack/react-query";

import { alerts, type SignalCalibrationTable } from "@/api/alerts";

/** Per-detector calibration table (base_rate, beta-stripped skill, edge, honesty
 *  tag). Detector-level and ~static between calibration regenerations, so cache
 *  it for a long time and share it across every open signal popup. */
export function useSignalCalibration() {
  return useQuery<SignalCalibrationTable>({
    queryKey: ["signals", "calibration"],
    queryFn: () => alerts.signalCalibration(),
    staleTime: 60 * 60_000, // 1h — the artifact changes only on recalibration
    gcTime: 2 * 60 * 60_000,
  });
}
