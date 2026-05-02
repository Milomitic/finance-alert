import { api } from "./client";
import type { SpotlightSummary } from "./types";

export const spotlight = {
  summary: () => api<SpotlightSummary>("/api/dashboard/spotlight"),
};
