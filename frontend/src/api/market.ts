import { api } from "./client";
import type { MarketSummary } from "./types";

export const market = {
  summary: () => api<MarketSummary>("/api/dashboard/market-summary"),
};
