import { api } from "./client";
import type { Alert, AlertList, DigestResult, ScanStatusInfo, ScanStopResultInfo, UnreadCount } from "./types";

export interface AlertListParams {
  /** Exact-match ticker filter (legacy — not used by the UI anymore;
   *  superseded by `q` for the column-header search). Kept on the
   *  type so existing callers and CSV exports still work. */
  ticker?: string;
  /** Substring search across ticker OR name. Folded into the AlertsTable
   *  Stock column header so the user filters from the same place that
   *  labels the column. */
  q?: string;
  rule_kind?: string;
  /** Tone filter: "bull" or "bear". Matched against snapshot.tone. */
  tone?: string;
  /** Minimum confidence score 0-100. Only alerts with confidence >= this are returned. */
  confidence_min?: number;
  /** Signal nature: 'continuazione' | 'inversione'. */
  nature?: string;
  date_from?: string; // ISO date
  date_to?: string;
  read?: boolean;
  archived?: boolean;
  limit?: number;
  offset?: number;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
}

function toQuery(params: AlertListParams): string {
  const sp = new URLSearchParams();
  if (params.ticker) sp.set("ticker", params.ticker);
  if (params.q) sp.set("q", params.q);
  if (params.rule_kind) sp.set("rule_kind", params.rule_kind);
  if (params.tone) sp.set("tone", params.tone);
  if (params.confidence_min !== undefined) sp.set("confidence_min", String(params.confidence_min));
  if (params.nature) sp.set("nature", params.nature);
  if (params.date_from) sp.set("date_from", params.date_from);
  if (params.date_to) sp.set("date_to", params.date_to);
  if (params.read !== undefined) sp.set("read", String(params.read));
  if (params.archived !== undefined) sp.set("archived", String(params.archived));
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  if (params.sort_by) sp.set("sort_by", params.sort_by);
  if (params.sort_dir) sp.set("sort_dir", params.sort_dir);
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
  /** Cancel the currently-running scan. Backend handles both live workers
   *  (cooperative cancel via in-memory flag) and stuck/orphan rows (force-
   *  close inline). Idempotent — safe to call when nothing is running. */
  scanStop: () =>
    api<ScanStopResultInfo>("/api/alerts/scan/stop", { method: "POST" }),
  sendDigest: () =>
    api<DigestResult>("/api/alerts/send-digest", {
      method: "POST",
      body: "{}",
    }),
  scanStatus: () => api<ScanStatusInfo>("/api/alerts/scan-status"),
};
