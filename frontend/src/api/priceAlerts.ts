import { api } from "./client";
import type {
  PriceAlert,
  PriceAlertCreate,
  PriceAlertUpdate,
} from "./types";

export const priceAlerts = {
  list: (ticker: string) =>
    api<PriceAlert[]>(
      `/api/stocks/${encodeURIComponent(ticker)}/price-alerts`
    ),
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
