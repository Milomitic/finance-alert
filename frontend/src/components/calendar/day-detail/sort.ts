import type { RiskTier } from "@/api/types";

/* ─── Earnings-table sort model ─────────────────────────────────────────── */
/* Extracted from DayDetailPanel.tsx (B4-11 split). Shared between the
 * composition root (which owns the sort state + the filter/sort memo)
 * and the EarningsTable presentation component (whose column headers
 * emit SortKey clicks). Pure types + constants — no React here.
 */

/** Sort dimensions surfaced as table columns. Phase 3G: dropped the
 *  forward-P/E and YoY-growth columns (those live on the stock detail
 *  page) and added Ultimo (eps_reported) / Atteso (eps_estimate) /
 *  Sorpresa (surprise_pct) so the earnings table mirrors the macro
 *  insight strip's columns. */
export type SortKey =
  | "ticker"
  | "marketcap"
  | "ultimo"        // eps_reported — null for upcoming
  | "atteso"        // eps_estimate
  | "sorpresa"      // surprise_pct — null for upcoming
  | "score"
  | "risk";
export type SortDir = "asc" | "desc";

export interface SortState {
  key: SortKey;
  dir: SortDir;
}

/** Default sort direction per column. Numeric "bigger = more interesting"
 *  columns default to desc. Ticker defaults to asc. */
export const DEFAULT_DIR: Record<SortKey, SortDir> = {
  ticker: "asc",
  marketcap: "desc",
  ultimo: "desc",
  atteso: "desc",
  sorpresa: "desc",
  score: "desc",
  risk: "asc",
};

/** Risk-tier ordinal for sort: conservative < moderate < aggressive. */
export const RISK_RANK: Record<RiskTier, number> = {
  conservative: 0,
  moderate: 1,
  aggressive: 2,
};
