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
export type StockSortBy = "ticker" | "name" | "market_cap" | "sector" | "exchange";
export type SortDir = "asc" | "desc";

export interface SearchParams {
  q?: string;
  exchange?: string[];
  sector?: string[];
  country?: string[];
  index?: string[];
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
  for (const v of params.country ?? []) sp.append("country", v);
  for (const v of params.index ?? []) sp.append("index", v);
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
