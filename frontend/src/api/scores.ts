import { api } from "./client";
import type {
  RiskTier,
  ScoreCategory,
  StockScore,
  TopPicks,
} from "./types";

export interface TopPicksParams {
  risk?: RiskTier;
  category?: ScoreCategory;
  /** Default 10 server-side, max 50. */
  limit?: number;
}

function toQuery(params: TopPicksParams): string {
  const sp = new URLSearchParams();
  if (params.risk) sp.set("risk", params.risk);
  if (params.category) sp.set("category", params.category);
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const scores = {
  forStock: (ticker: string) =>
    api<StockScore>(`/api/stocks/${encodeURIComponent(ticker)}/score`),
  /**
   * Force a fresh score recomputation for one stock and persist it. Used by
   * the "refresh score" button on the detail page when the persisted score
   * is stale (e.g. fundamentals were partial when the periodic scan ran).
   *
   * Backend: forces a fundamentals refetch BEFORE compute_score so a stale
   * L1 entry from a pre-fix hydration doesn't cause the recompute to
   * regenerate the same broken pillars. Returns the newly persisted score.
   */
  recomputeForStock: (ticker: string) =>
    api<StockScore>(
      `/api/stocks/${encodeURIComponent(ticker)}/score/recompute`,
      { method: "POST" },
    ),
  top: (opts: TopPicksParams = {}) =>
    api<TopPicks>(`/api/scores/top${toQuery(opts)}`),
};
