import { api } from "./client";
import type {
  FilterOptions,
  Stock,
  StockDetail,
  StockNews,
  StockSearch,
} from "./types";

/** Server-sortable columns. Must match backend `SORTABLE_COLUMNS` whitelist
 *  in stock_service.py. `change_pct` is NOT here — it's a client-side-only
 *  sort because the value comes from the market-stats snapshot, not the
 *  Stock table. */
export type StockSortBy =
  | "ticker"
  | "name"
  | "market_cap"
  | "sector"
  | "industry"
  | "exchange"
  | "composite"
  | "profitability"
  | "sustainability"
  | "growth"
  | "value"
  | "momentum"
  | "sentiment";
export type SortDir = "asc" | "desc";

export interface SearchParams {
  q?: string;
  exchange?: string[];
  sector?: string[];
  industry?: string[];
  country?: string[];
  index?: string[];
  /** Risk-tier filter — multi-select; empty / undefined = no filter. */
  risk?: ("conservative" | "moderate" | "aggressive")[];
  /** Minimum composite score (0–100). When set, unscored stocks are excluded. */
  min_score?: number;
  /** Maximum composite score (0–100). */
  score_max?: number;
  /** Per-pillar minimum scores (0–100). */
  profitability_min?: number;
  sustainability_min?: number;
  growth_min?: number;
  value_min?: number;
  momentum_min?: number;
  sentiment_min?: number;
  sort_by?: StockSortBy;
  sort_dir?: SortDir;
  limit?: number;
  offset?: number;
}

function toQuery(params: SearchParams): string {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  for (const v of params.exchange ?? []) sp.append("exchange", v);
  for (const v of params.sector ?? []) sp.append("sector", v);
  for (const v of params.industry ?? []) sp.append("industry", v);
  for (const v of params.country ?? []) sp.append("country", v);
  for (const v of params.index ?? []) sp.append("index", v);
  for (const v of params.risk ?? []) sp.append("risk", v);
  if (params.min_score !== undefined) sp.set("min_score", String(params.min_score));
  if (params.score_max !== undefined) sp.set("score_max", String(params.score_max));
  if (params.profitability_min !== undefined) sp.set("profitability_min", String(params.profitability_min));
  if (params.sustainability_min !== undefined) sp.set("sustainability_min", String(params.sustainability_min));
  if (params.growth_min !== undefined) sp.set("growth_min", String(params.growth_min));
  if (params.value_min !== undefined) sp.set("value_min", String(params.value_min));
  if (params.momentum_min !== undefined) sp.set("momentum_min", String(params.momentum_min));
  if (params.sentiment_min !== undefined) sp.set("sentiment_min", String(params.sentiment_min));
  if (params.sort_by) sp.set("sort_by", params.sort_by);
  if (params.sort_dir) sp.set("sort_dir", params.sort_dir);
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const stocks = {
  search: (params: SearchParams = {}, signal?: AbortSignal) =>
    api<StockSearch>(`/api/stocks/search${toQuery(params)}`, { signal }),
  filters: () => api<FilterOptions>("/api/stocks/filters"),
  byTicker: (ticker: string) =>
    api<Stock>(`/api/stocks/${encodeURIComponent(ticker)}`),
  detail: (ticker: string, range = "1y") =>
    api<StockDetail>(
      `/api/stocks/${encodeURIComponent(ticker)}/detail?range=${range}`
    ),
  news: (ticker: string, limit = 5) =>
    api<StockNews>(
      `/api/stocks/${encodeURIComponent(ticker)}/news?limit=${limit}`
    ),
};
