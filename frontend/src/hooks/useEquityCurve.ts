import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

export interface EquityPoint {
  date: string;
  equity: number;
  equity_mkt_neutral: number;
}

export interface EquityCurve {
  points: EquityPoint[];
  n_signals: number;
  total_return_pct: number;
  mkt_neutral_return_pct: number;
  win_rate_pct: number;
  avg_return_pct: number;
  max_drawdown_pct: number;
  horizon_days: number;
  detectors: string[];
}

export interface EquityFilters {
  horizonDays: number; // 5 | 21
  detector: string; // "" = all
  tone: string; // "" | "bull" | "bear"
  regime: string; // "" | "bull" | "bear" | "flat"
  strengthMin: number; // 0 = no filter
}

/** Hypothetical cumulative equity of following every matured signal matching
 *  the filters (growth-of-1 illustration; see the backend docstring). */
export function useEquityCurve(f: EquityFilters) {
  const params = new URLSearchParams();
  params.set("horizon_days", String(f.horizonDays));
  if (f.detector) params.set("detector", f.detector);
  if (f.tone) params.set("tone", f.tone);
  if (f.regime) params.set("regime", f.regime);
  if (f.strengthMin > 0) params.set("strength_min", String(f.strengthMin));
  return useQuery({
    queryKey: ["equity-curve", f],
    queryFn: () =>
      api<EquityCurve>(`/api/rule-performance/equity-curve?${params.toString()}`),
    staleTime: 60_000,
  });
}
