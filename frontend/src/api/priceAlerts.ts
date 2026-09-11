import { api } from "./client";
import type { PriceAlert, PriceAlertCreate, PriceAlertUpdate } from "./types";

export const priceAlerts = {
  list: (ticker: string, signal?: AbortSignal) =>
    api<PriceAlert[]>(
      `/api/stocks/${encodeURIComponent(ticker)}/price-alerts`, { signal }),
  /** Tutti i price alert ATTIVI (abilitati e non ancora scattati) in una
   *  sola chiamata — alimenta la campanella dello screener senza N+1. */
  listActive: (signal?: AbortSignal) => api<PriceAlert[]>("/api/price-alerts?active=true", { signal }),
  create: (ticker: string, body: PriceAlertCreate) =>
    api<PriceAlert>(
      `/api/stocks/${encodeURIComponent(ticker)}/price-alerts`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),
  update: (id: number, body: PriceAlertUpdate) =>
    api<PriceAlert>(`/api/price-alerts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  remove: (id: number) =>
    api<void>(`/api/price-alerts/${id}`, { method: "DELETE" }),
};
