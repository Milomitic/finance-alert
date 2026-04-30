import { api } from "./client";
import type { FilterOptions, Stock, StockSearch } from "./types";

export interface SearchParams {
  q?: string;
  exchange?: string[];
  sector?: string[];
  country?: string[];
  index?: string[];
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
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const stocks = {
  search: (params: SearchParams = {}, signal?: AbortSignal) =>
    api<StockSearch>(`/api/stocks/search${toQuery(params)}`, { signal }),
  filters: () => api<FilterOptions>("/api/stocks/filters"),
  byTicker: (ticker: string) => api<Stock>(`/api/stocks/${encodeURIComponent(ticker)}`),
};
