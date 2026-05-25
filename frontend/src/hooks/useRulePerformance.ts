import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

export interface WindowStats {
  count: number;
  mean_pct: number | null;
  median_pct: number | null;
  hit_rate: number | null;
}

export interface RulePerformanceItem {
  rule_kind: string;
  tone: "bullish" | "bearish" | "neutral";
  total_alerts: number;
  /** Window key is the day count as a string ("1", "5", "20"). */
  stats: Record<string, WindowStats>;
}

export interface RulePerformanceList {
  days: number;
  items: RulePerformanceItem[];
}

/** Fetch per-rule forward-return stats. `days` controls the lookback
 *  window; default 90 means "alerts from the last 3 months". */
export function useRulePerformance(days: number = 90) {
  return useQuery({
    queryKey: ["rule-performance", days],
    queryFn: () =>
      api<RulePerformanceList>(`/api/rule-performance?days=${days}`),
    // Stats don't change intra-session unless a new scan fires; let
    // the cache hold for 5 minutes.
    staleTime: 5 * 60 * 1000,
  });
}

export interface CalibrationBucket {
  label: string;
  count: number;
  hit_rate: number | null;
  mean_pct: number | null;
  median_pct: number | null;
}

export interface CalibrationSeedCell {
  count: number;
  hit_rate: number | null;
  mean_pct: number | null;
}
export interface CalibrationSeed {
  window: number;
  by_horizon: Record<string, CalibrationSeedCell>;
  by_confidence: Record<string, CalibrationSeedCell>;
  by_confidence_horizon: Record<string, CalibrationSeedCell>;
  by_nature: Record<string, CalibrationSeedCell>;
}
export interface Calibration {
  days: number;
  window: number;
  by_confidence: CalibrationBucket[];
  by_nature: CalibrationBucket[];
  by_horizon: CalibrationBucket[];
  /** Backtest-derived reference (populates the panel immediately while live
   *  calibration matures). Null if the seed file is absent. */
  backtest_seed: CalibrationSeed | null;
}

export interface CalibrationCurve {
  window?: number;
  by_horizon?: Record<string, CalibrationSeedCell>;
  by_confidence?: Record<string, CalibrationSeedCell>;
  by_confidence_horizon?: Record<string, CalibrationSeedCell>;
  by_nature?: Record<string, CalibrationSeedCell>;
}

/** Lightweight calibration curve (backtest seed only, no heavy recompute) used
 *  to annotate any signal with a calibrated probability. Cached aggressively. */
export function useCalibrationCurve() {
  return useQuery({
    queryKey: ["calibration-curve"],
    queryFn: () => api<CalibrationCurve>("/api/rule-performance/calibration-curve"),
    staleTime: 60 * 60 * 1000,
  });
}

/** Realized directional hit-rate + forward return bucketed by confidence and
 *  by nature, at a fixed horizon. Matures over forward time. */
export function useCalibration(days = 365, horizon = 20) {
  return useQuery({
    queryKey: ["calibration", days, horizon],
    queryFn: () =>
      api<Calibration>(`/api/rule-performance/calibration?days=${days}&window=${horizon}`),
    staleTime: 5 * 60 * 1000,
  });
}
