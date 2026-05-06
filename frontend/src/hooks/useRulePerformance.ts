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
