import { api } from "./client";
import type { DashboardSummary } from "./types";

/** One recent analyst rating action — mirrors backend
 *  `schemas.dashboard.AnalystActionOut`. */
export type AnalystAction = {
  ticker: string;
  name: string | null;
  date: string; // ISO YYYY-MM-DD
  firm: string;
  to_grade: string;
  from_grade: string;
  action: string; // up | down | init | main | reit | ...
  current_price_target: number | null;
  from_news: boolean;
};

export const dashboard = {
  summary: () => api<DashboardSummary>("/api/dashboard/summary"),
  analystActions: (limit = 40) =>
    api<AnalystAction[]>(`/api/dashboard/analyst-actions?limit=${limit}`),
};
