import { api } from "./client";
import type { DashboardSummary } from "./types";

/** One recent analyst rating action — mirrors backend
 *  `schemas.dashboard.AnalystActionOut`. */
export type AnalystAction = {
  ticker: string;
  name: string | null;
  date: string; // ISO YYYY-MM-DD
  firm: string;
  to_grade: string;
  from_grade: string;
  action: string; // up | down | init | main | reit | ...
  current_price_target: number | null;
  /** Same firm's previous target — when present the dashboard chip
   *  renders "$287 → $296" instead of a bare current value. */
  prior_price_target?: number | null;
  /** yfinance's separate price-target axis: "Raises" | "Lowers" |
   *  "Maintains" | "Initiates" | null. Distinct from `action` (a
   *  Maintain rating can pair with a target Raise). */
  price_target_action?: string | null;
  /** Latest stored close of the stock (same major unit as the target).
   *  Lets the card show the target's implied upside vs current price.
   *  null when the stock has no stored OHLCV. */
  current_price?: number | null;
  from_news: boolean;
};

/** One US pre-market gainer/loser — mirrors backend
 *  `schemas.dashboard.PremarketMoverOut`. */
export type PremarketMover = {
  ticker: string;
  name: string | null;
  price: number;
  prev_close: number;
  change_pct: number;
  volume: number | null; // summed pre-market volume (null = n/d)
};

/** Mirrors `schemas.dashboard.PremarketMoversOut`. `available` is the
 *  single flag the card keys on: render only when true. */
export type PremarketMovers = {
  available: boolean;
  market_open: boolean;
  as_of: string | null;
  computed_at: string | null;
  refreshing: boolean;
  progress_pct: number;
  gainers: PremarketMover[];
  losers: PremarketMover[];
};

export const dashboard = {
  summary: () => api<DashboardSummary>("/api/dashboard/summary"),
  analystActions: (limit = 40) =>
    api<AnalystAction[]>(`/api/dashboard/analyst-actions?limit=${limit}`),
  premarketMovers: () =>
    api<PremarketMovers>("/api/dashboard/premarket-movers"),
  refreshPremarketMovers: () =>
    api<{ accepted: boolean }>(
      "/api/dashboard/premarket-movers/refresh",
      { method: "POST" },
    ),
};
