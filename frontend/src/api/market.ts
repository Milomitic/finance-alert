import { api } from "./client";
import type { MarketSummary } from "./types";

export const market = {
  summary: (signal?: AbortSignal) => api<MarketSummary>("/api/dashboard/market-summary", { signal }),
};
