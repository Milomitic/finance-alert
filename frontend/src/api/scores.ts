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
  top: (opts: TopPicksParams = {}) =>
    api<TopPicks>(`/api/scores/top${toQuery(opts)}`),
};
