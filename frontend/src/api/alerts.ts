import { api } from "./client";
import type { Alert, AlertList, DigestResult, UnreadCount } from "./types";

export interface AlertListParams {
  ticker?: string;
  rule_kind?: string;
  date_from?: string; // ISO date
  date_to?: string;
  read?: boolean;
  archived?: boolean;
  limit?: number;
  offset?: number;
}

function toQuery(params: AlertListParams): string {
  const sp = new URLSearchParams();
  if (params.ticker) sp.set("ticker", params.ticker);
  if (params.rule_kind) sp.set("rule_kind", params.rule_kind);
  if (params.date_from) sp.set("date_from", params.date_from);
  if (params.date_to) sp.set("date_to", params.date_to);
  if (params.read !== undefined) sp.set("read", String(params.read));
  if (params.archived !== undefined) sp.set("archived", String(params.archived));
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const alerts = {
  list: (params: AlertListParams = {}) =>
    api<AlertList>(`/api/alerts${toQuery(params)}`),
  unreadCount: () => api<UnreadCount>("/api/alerts/unread-count"),
  patch: (id: number, body: { read?: boolean; archived?: boolean }) =>
    api<Alert>(`/api/alerts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  bulk: (ids: number[], action: "mark_read" | "mark_unread" | "archive" | "unarchive") =>
    api<{ affected: number }>("/api/alerts/bulk", {
      method: "POST",
      body: JSON.stringify({ ids, action }),
    }),
  exportCsvUrl: (params: AlertListParams = {}) =>
    `/api/alerts/export.csv${toQuery(params)}`,
  scan: (stockIds?: number[]) =>
    api<{ accepted: boolean }>("/api/alerts/scan", {
      method: "POST",
      body: JSON.stringify(stockIds ? { stock_ids: stockIds } : {}),
    }),
  sendDigest: () =>
    api<DigestResult>("/api/alerts/send-digest", {
      method: "POST",
      body: "{}",
    }),
};
