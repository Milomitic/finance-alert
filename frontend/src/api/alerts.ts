import { api } from "./client";
import type { Alert, AlertList, DigestResult, ScanStatusInfo, ScanStopResultInfo } from "./types";

export interface ConfluenceComponent {
  alert_id: number;
  rule_kind: string;
  signal_name: string;
  /** Per-signal Forza (pattern strength). Optional `strength` is the new
   *  primary; `confidence` stays as the legacy fallback (transitional alias). */
  strength?: number;
  confidence: number;
  /** Per-signal Probabilità (historical hit-rate). Optional — absent on
   *  legacy clusters whose components predate the two-score split. */
  probability?: number;
  tone: string;
  horizon: string;
  signal_date: string | null;
}

export interface Confluence {
  ticker: string;
  name: string | null;
  direction: string;        // prevailing side: "bull" | "bear"
  strength: number;
  n_signals: number;
  /** De-correlated independent-evidence count (distinct detector families +
   *  small same-family discount). ≤ n_signals; what drives `strength`. */
  effective_n?: number;
  bull_strength: number;
  bear_strength: number;
  contested: boolean;
  multi_horizon: boolean;
  horizons: string[];
  components: ConfluenceComponent[];
}

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
  /** Minimum Forza (pattern strength) 0-100. Only alerts with strength >= this
   *  are returned. The new primary strength filter. */
  strength_min?: number;
  /** Minimum Probabilità (historical hit-rate) 0-100. Only alerts with
   *  probability >= this are returned. */
  probability_min?: number;
  /** Signal nature: 'continuazione' | 'inversione'. */
  nature?: string;
  /** Realised outcome filter: 'hit' | 'miss' | 'pending' (in maturazione).
   *  Joined server-side against the signal_outcomes warehouse. */
  outcome?: string;
  /** Signal horizon filter: 'short' | 'medium' | 'long' (snapshot.horizon). */
  horizon?: string;
  date_from?: string; // ISO date (inclusive)
  /** ISO date, INCLUSIVE on the client ("fino al giorno X compreso"). The
   *  backend filter is exclusive (`triggered_at < date_to`), so `toQuery`
   *  sends the day AFTER at the wire boundary. */
  date_to?: string;
  archived?: boolean;
  limit?: number;
  offset?: number;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
}

/** Day after an ISO date (local calendar). Used to convert the UI's
 *  inclusive date_to into the backend's exclusive `< date_to` filter. */
function isoDayAfter(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  d.setDate(d.getDate() + 1);
  return d.toLocaleDateString("en-CA"); // YYYY-MM-DD
}

function toQuery(params: AlertListParams): string {
  const sp = new URLSearchParams();
  if (params.ticker) sp.set("ticker", params.ticker);
  if (params.q) sp.set("q", params.q);
  if (params.rule_kind) sp.set("rule_kind", params.rule_kind);
  if (params.tone) sp.set("tone", params.tone);
  if (params.strength_min !== undefined) sp.set("strength_min", String(params.strength_min));
  if (params.probability_min !== undefined) sp.set("probability_min", String(params.probability_min));
  if (params.nature) sp.set("nature", params.nature);
  if (params.outcome) sp.set("outcome", params.outcome);
  if (params.horizon) sp.set("horizon", params.horizon);
  if (params.date_from) sp.set("date_from", params.date_from);
  if (params.date_to) sp.set("date_to", isoDayAfter(params.date_to));
  if (params.archived !== undefined) sp.set("archived", String(params.archived));
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  if (params.sort_by) sp.set("sort_by", params.sort_by);
  if (params.sort_dir) sp.set("sort_dir", params.sort_dir);
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Per-detector calibration facts (Engine Quality v1). Detector-level, so a
 *  single fetch covers every alert of that detector. */
export interface DetectorCalibration {
  base_rate: number;
  /** Market-neutral hit-rate (beta-stripped) — the honest "skill". null if the
   *  artifact lacks it. */
  skill: number | null;
  edge_pct: number | null;
  n: number | null;
  horizon_days: number | null;
  tag: "coinflip" | "negative" | "edge" | null;
}
export interface SignalCalibrationTable {
  version: string | null;
  detectors: Record<string, DetectorCalibration>;
}

export const alerts = {
  list: (params: AlertListParams = {}) =>
    api<AlertList>(`/api/alerts${toQuery(params)}`),
  patch: (id: number, body: { archived?: boolean }) =>
    api<Alert>(`/api/alerts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  bulk: (ids: number[], action: "archive" | "unarchive") =>
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
  /** Synchronously run the signal engine for ONE stock over its stored OHLCV
   *  and persist new signal alerts. Returns {added, total}. Used by the
   *  per-stock "processa segnali" button on the detail page. */
  scanStock: (ticker: string) =>
    api<{ added: number; total: number }>(
      `/api/alerts/scan-stock/${encodeURIComponent(ticker)}`,
      { method: "POST" },
    ),
  sendDigest: () =>
    api<DigestResult>("/api/alerts/send-digest", {
      method: "POST",
      body: "{}",
    }),
  scanStatus: () => api<ScanStatusInfo>("/api/alerts/scan-status"),
  /** Per-detector calibration table (base_rate, beta-stripped skill, edge_pct,
   *  n, honesty tag). Detector-level + ~static, so cache it aggressively. */
  signalCalibration: () =>
    api<SignalCalibrationTable>("/api/alerts/signal-calibration"),
  /** Confluence clusters: active signal alerts grouped by ticker+direction,
   *  strongest first. `days` = active-window length (default 7). */
  confluence: (days = 7) =>
    api<Confluence[]>(`/api/alerts/confluence?days=${days}`),
};
