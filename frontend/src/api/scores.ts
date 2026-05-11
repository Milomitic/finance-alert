import { api } from "./client";
import type {
  RiskTier,
  ScanStatusInfo,
  ScanStopResultInfo,
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
  /**
   * Force a fresh score recomputation for one stock and persist it. Used by
   * the "refresh score" button on the detail page when the persisted score
   * is stale (e.g. fundamentals were partial when the periodic scan ran).
   *
   * Backend: forces a fundamentals refetch BEFORE compute_score so a stale
   * L1 entry from a pre-fix hydration doesn't cause the recompute to
   * regenerate the same broken pillars. Returns the newly persisted score.
   */
  recomputeForStock: (ticker: string) =>
    api<StockScore>(
      `/api/stocks/${encodeURIComponent(ticker)}/score/recompute`,
      { method: "POST" },
    ),
  /**
   * Trigger a background recompute of every stock's composite score. Returns
   * 202 immediately; live progress is exposed by `recomputeStatus()` and
   * rendered in the persistent toast (mirror of the alert-scan flow).
   *
   * Backend dedupes: if a recompute is already running, returns 409 with
   * an explanatory message — caller surfaces it via toast.error.
   */
  recomputeAll: () =>
    api<{ accepted: true }>(`/api/scores/recompute-all`, { method: "POST" }),
  /** Latest ScanRun row where kind='score_recompute'. Polled by the toast hook. */
  recomputeStatus: () => api<ScanStatusInfo>(`/api/scores/recompute-status`),
  /** Cooperative cancel (or force-close on stale) of the running recompute. */
  recomputeStop: () =>
    api<ScanStopResultInfo>(`/api/scores/recompute-stop`, { method: "POST" }),
  top: (opts: TopPicksParams = {}) =>
    api<TopPicks>(`/api/scores/top${toQuery(opts)}`),
};
