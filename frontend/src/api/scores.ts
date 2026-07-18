import { api } from "./client";
import type {
  RiskTier,
  ScanStatusInfo,
  ScanStopResultInfo,
  ScoreCategory,
  ScoreHistoryOut,
  ScoreIcReport,
  ScoreLens,
  StockScore,
  TechnicalScoreDetail,
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
  technicalForStock: (ticker: string) =>
    api<TechnicalScoreDetail>(`/api/stocks/${encodeURIComponent(ticker)}/technical`),
  /**
   * Daily composite snapshots (score_history) for one lens, ascending,
   * capped to the last `days` days (7-365). Feeds the sparkline on the
   * score card; `points` may hold 0-1 entries while history accrues.
   */
  scoreHistory: (ticker: string, lens: ScoreLens = "qualita", days = 180) =>
    api<ScoreHistoryOut>(
      `/api/stocks/${encodeURIComponent(ticker)}/score-history?lens=${lens}&days=${days}`,
    ),
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
   * Force a single-stock technical-score recomputation from stored OHLCV and
   * persist it. Used by the "refresh" button on the technical card when the
   * scan-time score is missing or stale. Returns the freshly persisted score.
   *
   * Note: the cross-sectional relative-strength percentile is reused from the
   * prior row (recomputing it needs the whole universe); the four price
   * dimensions are recomputed from the latest stored bars.
   */
  recomputeTechnicalForStock: (ticker: string) =>
    api<TechnicalScoreDetail>(
      `/api/stocks/${encodeURIComponent(ticker)}/technical/recompute`,
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
  /** The pillar-IC transparency study (why the composite is a descriptor,
   *  not a return predictor). Static artifact — cache hard. */
  icReport: () => api<ScoreIcReport>(`/api/scores/ic-report`),
};
