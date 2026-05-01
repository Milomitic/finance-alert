import { api } from "./client";
import type { DashboardSummary } from "./types";

export const dashboard = {
  summary: () => api<DashboardSummary>("/api/dashboard/summary"),
};
