import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

/** A derived engine-health flag (triage item) from the KPI series. */
export interface KpiFlag {
  level: "error" | "warn" | "ok";
  code: string;
  title: string;
  detail: string;
}

/** Live "shape" of what the engine is currently emitting. */
export interface KpiSignalPopulation {
  total: number;
  by_detector: Record<string, number>;
  by_tone: Record<string, number>;
  by_horizon: Record<string, number>;
  by_confidence: Record<string, number>;
}

export interface KpiDataSource {
  source: string;
  op: string;
  success: number;
  failure: number;
  success_rate: number | null;
  health: string;
}

export interface KpiCalibrationBucket {
  label: string;
  count: number;
  hit_rate: number | null;
  mean_pct: number | null;
}

export interface KpiScanMetrics {
  scan_run_id?: number;
  trigger?: string;
  stocks_scanned?: number | null;
  stocks_skipped?: number | null;
  alerts_fired?: number | null;
  duration_s?: number | null;
  signals?: KpiSignalPopulation;
  data_sources?: KpiDataSource[];
}

export interface KpiRollupMetrics {
  calibration?: {
    window?: number;
    by_confidence?: KpiCalibrationBucket[];
    by_horizon?: KpiCalibrationBucket[];
    by_nature?: KpiCalibrationBucket[];
  };
  confluence?: {
    n_clusters: number;
    multi_horizon_rate: number | null;
    contested_rate: number | null;
  };
  signals?: KpiSignalPopulation;
  data_sources?: KpiDataSource[];
}

export interface KpiSnapshot<M> {
  id: number;
  captured_at: string;
  scope: string | null;
  metrics: M;
}

export interface KpiMonitor {
  scans: KpiSnapshot<KpiScanMetrics>[];
  rollups: KpiSnapshot<KpiRollupMetrics>[];
  flags: KpiFlag[];
}

/** Engine-monitoring time series + health flags for the "Salute motori"
 *  panel. Cheap read (capture happens at scan-end + daily cron), cached 5min. */
export function useKpiMonitor(days = 90) {
  return useQuery({
    queryKey: ["kpi-monitor", days],
    queryFn: () => api<KpiMonitor>(`/api/kpi/monitor?days=${days}`),
    staleTime: 5 * 60 * 1000,
  });
}
