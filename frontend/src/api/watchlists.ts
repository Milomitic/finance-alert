import { api } from "./client";
import type { WatchlistDetail, WatchlistSummary } from "./types";

export interface WatchlistCreatePayload {
  name: string;
  description?: string | null;
  stock_ids?: number[];
}

export interface WatchlistUpdatePayload {
  name?: string;
  description?: string | null;
}

export const watchlists = {
  list: () => api<WatchlistSummary[]>("/api/watchlists"),
  create: (payload: WatchlistCreatePayload) =>
    api<WatchlistDetail>("/api/watchlists", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  get: (id: number) => api<WatchlistDetail>(`/api/watchlists/${id}`),
  patch: (id: number, payload: WatchlistUpdatePayload, signal?: AbortSignal) =>
    api<WatchlistDetail>(`/api/watchlists/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
      signal,
    }),
  delete: (id: number) =>
    api<void>(`/api/watchlists/${id}`, {
      method: "DELETE",
    }),
  addItems: (id: number, stockIds: number[]) =>
    api<{ added: number }>(`/api/watchlists/${id}/items`, {
      method: "POST",
      body: JSON.stringify({ stock_ids: stockIds }),
    }),
  removeItem: (id: number, stockId: number) =>
    api<void>(`/api/watchlists/${id}/items/${stockId}`, {
      method: "DELETE",
    }),
  bulkDelete: (id: number, stockIds: number[]) =>
    api<{ removed: number }>(`/api/watchlists/${id}/items/bulk-delete`, {
      method: "POST",
      body: JSON.stringify({ stock_ids: stockIds }),
    }),
};
