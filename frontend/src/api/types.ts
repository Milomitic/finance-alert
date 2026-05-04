export interface Me {
  username: string;
}

export interface Stock {
  id: number;
  ticker: string;
  exchange: string;
  name: string;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string | null;
  market_cap: number | null;
}

export interface StockSearch {
  items: Stock[];
  total: number;
  has_more: boolean;
}

export interface IndexOption {
  code: string;
  name: string;
}

export interface FilterOptions {
  exchanges: string[];
  sectors: string[];
  countries: string[];
  indices: IndexOption[];
}

export interface WatchlistSummary {
  id: number;
  name: string;
  description: string | null;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface WatchlistDetail {
  id: number;
  name: string;
  description: string | null;
  stocks: Stock[];
  created_at: string;
  updated_at: string;
}

export interface IndexStatus {
  index_code: string;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_status: string | null;
  stocks_added: number | null;
  stocks_updated: number | null;
  stocks_removed: number | null;
  error_message: string | null;
}

export interface CatalogStatus {
  indices: IndexStatus[];
}

export type RuleKind =
  | "rsi_oversold"
  | "rsi_overbought"
  | "golden_cross"
  | "death_cross"
  | "volume_spike"
  | "breakout"
  | "macd_bullish_cross"
  | "macd_bearish_cross"
  | "bollinger_squeeze"
  | "bollinger_breakout"
  | "composite";

export type RuleExpressionAtomic = {
  op: "atomic";
  kind: string;
  params: Record<string, unknown>;
};

export type RuleExpressionComposite = {
  op: "and" | "or";
  children: RuleExpressionNode[];
};

export type RuleExpressionNode = RuleExpressionAtomic | RuleExpressionComposite;

export interface RuleCatalogEntry {
  kind: string;
  label: string;
  description: string;
  default_params: Record<string, unknown>;
}

export interface RulePreviewSnapshotAtomic {
  op: "atomic";
  kind: string;
  params: Record<string, unknown>;
  matched?: boolean;
  snapshot?: Record<string, unknown>;
  error?: string;
}

export interface RulePreviewSnapshotComposite {
  op: "and" | "or";
  matched: boolean;
  children: RulePreviewSnapshotNode[];
}

export type RulePreviewSnapshotNode =
  | RulePreviewSnapshotAtomic
  | RulePreviewSnapshotComposite;

export interface RulePreviewResponse {
  matched: boolean;
  snapshot: RulePreviewSnapshotNode;
}

export interface Rule {
  id: number;
  watchlist_id: number | null;
  kind: RuleKind;
  params: Record<string, unknown>;
  enabled: boolean;
  expression: RuleExpressionNode | null;
  created_at: string;
  updated_at: string;
}

export interface Alert {
  id: number;
  rule_id: number;
  /** ISO date (YYYY-MM-DD) of the market-data bar where the rule's
   *  condition matched. May differ from `triggered_at` (the wall-clock
   *  moment the row was created): a scan run on Monday morning may detect
   *  a signal whose underlying bar closed Friday. NULL only for legacy
   *  rows from before this column existed. */
  signal_date?: string | null;
  rule_kind: RuleKind | null;
  stock_id: number;
  ticker: string | null;
  name: string | null;
  triggered_at: string;
  trigger_price: number;
  snapshot: Record<string, unknown>;
  read_at: string | null;
  archived_at: string | null;
}

export interface AlertList {
  items: Alert[];
  total: number;
  has_more: boolean;
}

export interface UnreadCount {
  count: number;
}

export interface DigestResult {
  sent: boolean;
  alerts_count: number;
  reason: string | null;
}

export type ScanStatus = "running" | "success" | "failed";
export type ScanTrigger = "cron" | "manual";
export type ScanPhase = "fetching" | "evaluating";

export interface ScanStatusInfo {
  is_running: boolean;
  last_run_id: number | null;
  trigger: ScanTrigger | null;
  status: ScanStatus | null;
  phase: ScanPhase | null;
  started_at: string | null;
  completed_at: string | null;
  /** Last time the worker reported progress (heartbeat). NULL only for runs
   *  created before the heartbeat column was added. UI uses this to detect
   *  stuck/orphan scans without trusting the wall clock. */
  last_progress_at: string | null;
  progress_done: number;
  progress_total: number;
  stocks_scanned: number | null;
  stocks_skipped: number | null;
  alerts_fired: number | null;
  error_message: string | null;
  /** True when status === 'running' but no heartbeat for >2 min. The UI shows
   *  a "Bloccato — clicca Termina" warning + Stop CTA when this is set. */
  is_stale: boolean;
  /** Computed by backend so client clocks don't drift. Used to cap the
   *  displayed running-duration when the worker is stuck (otherwise the
   *  counter would grow forever). */
  seconds_since_last_progress: number | null;
}

export interface ScanStopResultInfo {
  stopped_run_id: number | null;
  was_running: boolean;
  was_stale: boolean;
  message: string;
}

export interface KpiSummary {
  alerts_last_24h: number;
  alerts_prev_24h: number;
  alerts_unread: number;
  stocks_monitored: number;
  indices_count: number;
  last_scan: ScanStatusInfo | null;
  next_scan_at: string | null;
  next_digest_at: string | null;
}

export interface AlertsByDayPoint {
  date: string; // ISO date "YYYY-MM-DD"
  count: number;
  by_kind: Record<string, number>;
}

export interface TopStock {
  stock_id: number;
  ticker: string;
  name: string | null;
  alert_count: number;
  top_kind: string | null;
}

export interface SystemStatus {
  scheduler_running: boolean;
  scan_alerts_next_run: string | null;
  send_digest_next_run: string | null;
  refresh_catalog_next_run: string | null;
  telegram_configured: boolean;
  last_digest_sent_at: string | null;
}

export interface DashboardSummary {
  kpis: KpiSummary;
  alerts_by_day: AlertsByDayPoint[];
  top_stocks_30d: TopStock[];
  recent_alerts: Alert[];
  system_status: SystemStatus;
}

// === Fase 3A-bis: Market Dashboard ===

export interface MarketGlobal {
  stocks_total: number;
  stocks_with_data: number;
  advancers: number;
  decliners: number;
  unchanged: number;
  avg_change_pct: number;
  pct_above_sma200: number;
  pct_above_sma50: number;
  rsi_oversold_count: number;
  rsi_overbought_count: number;
  near_52w_high_count: number;
  near_52w_low_count: number;
  mood: "bullish" | "neutral" | "bearish";
}

export interface IndexBreadth {
  code: string;
  name: string;
  n: number;
  pct_above_sma200: number | null;
  pct_above_sma50: number | null;
  rsi_oversold_count: number;
  rsi_overbought_count: number;
  avg_change_pct: number | null;
  total_market_cap?: number | null;
  advancers: number;
  decliners: number;
  new_52w_highs: number;
  new_52w_lows: number;
  volume_spikes_count: number;
}

export interface RsiDistribution {
  all: number[];
  by_index: Record<string, number[]>;
}

export interface SectorBreadth {
  sector: string;
  n_stocks: number;
  avg_change_pct: number;
  pct_above_sma200: number;
}

export interface Mover {
  ticker: string;
  name: string;
  index: string | null;
  sector: string | null;
  change_pct: number | null;
  change_pct_5d?: number | null;
  change_pct_20d?: number | null;
  last_close: number;
  prev_close: number | null;
  sparkline?: number[];  // last ~30 close prices for the row's faded background trend
}

export interface VolumeSpike extends Mover {
  vol_ratio: number;
}

export interface MoversBlock {
  gainers: Mover[];
  losers: Mover[];
  gainers_5d?: Mover[];
  losers_5d?: Mover[];
  gainers_20d?: Mover[];
  losers_20d?: Mover[];
  volume_spikes: VolumeSpike[];
  new_52w_high: Mover[];
  new_52w_low: Mover[];
}

export interface TreemapLeaf {
  ticker: string;
  index: string | null;
  sector: string | null;
  market_cap: number;
  change_pct: number;
}

export interface MarketSummary {
  available: boolean;
  is_stale: boolean;
  reason?: string | null;
  computed_at?: string | null;
  scan_run_id?: number | null;
  global?: MarketGlobal;
  by_index?: IndexBreadth[];
  rsi_distribution?: RsiDistribution;
  sectors?: SectorBreadth[];
  movers?: MoversBlock;
  treemap?: TreemapLeaf[];
}

// === Fase 3B: Stock Detail ===

export interface OhlcvBar {
  date: string;     // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorPoint {
  date: string;
  value: number | null;
}

/** Actual periods used to compute the indicator series for the requested
 *  range. The series-key names (sma20/sma50/sma200, rsi14) are SLOT names —
 *  the real periods adapt per range. The UI reads this to label toggles
 *  with the actual values used (e.g. "SMA 10" on a 1m chart). */
export interface IndicatorPeriods {
  sma_fast: number;
  sma_mid: number;
  sma_slow: number;
  rsi: number;
  bb_period: number;
  bb_k: number;
  macd_fast: number;
  macd_slow: number;
  macd_signal: number;
}

export interface IndicatorSeries {
  sma20?: IndicatorPoint[];
  sma50: IndicatorPoint[];
  sma200: IndicatorPoint[];
  rsi14: IndicatorPoint[];
  bb_upper?: IndicatorPoint[];
  bb_middle?: IndicatorPoint[];
  bb_lower?: IndicatorPoint[];
  macd_line?: IndicatorPoint[];
  macd_signal?: IndicatorPoint[];
  macd_hist?: IndicatorPoint[];
  /** Optional for back-compat with older API responses; new responses always
   *  include it. UI falls back to default labels when missing. */
  periods?: IndicatorPeriods;
}

export interface StockKpis {
  last_close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  high_52w: number | null;
  low_52w: number | null;
  vol_avg_20: number | null;
  vol_today: number | null;
  vol_ratio: number | null;
}

export interface EffectiveRule {
  kind: string;
  enabled: boolean;
  params: Record<string, unknown>;
  source: "tier1" | "tier2";
  watchlist_name: string | null;
}

export interface StockDetail {
  stock: Stock;
  ohlcv: OhlcvBar[];
  indicators: IndicatorSeries;
  kpis: StockKpis;
  effective_rules: EffectiveRule[];
  alerts_history: Alert[];
}

export interface StockNewsItem {
  title: string;
  link: string;
  publisher: string;
  published_at: string | null;
}

export interface StockNews {
  items: StockNewsItem[];
}

export interface PriceAlert {
  id: number;
  stock_id: number;
  target_price: number;
  direction: "above" | "below";
  enabled: boolean;
  note: string | null;
  triggered_at: string | null;
  created_at: string;
}

export interface PriceAlertCreate {
  target_price: number;
  direction: "above" | "below";
  note?: string | null;
}

export interface PriceAlertUpdate {
  enabled?: boolean;
  target_price?: number;
  direction?: "above" | "below";
  note?: string | null;
}

export type SpotlightCardType = "top_gainer" | "top_loser" | "most_alerted_7d" | "vol_spike";

export interface SpotlightCard {
  type: SpotlightCardType;
  ticker: string;
  last_close: number | null;
  sparkline: number[];
  change_pct?: number | null;
  vol_ratio?: number | null;
  alerts_count?: number | null;
}

export interface SpotlightSummary {
  cards: SpotlightCard[];
}


export interface FundamentalsAnnual {
  fiscal_year_end: string;
  revenue: number | null;
  net_income: number | null;
  eps: number | null;
}

export interface FundamentalsQuarterly {
  fiscal_quarter_end: string;
  revenue: number | null;
  eps: number | null;
}

export interface FundamentalsEarnings {
  date: string;
  eps_estimate: number | null;
  eps_reported: number | null;
  surprise_pct: number | null;
  revenue_estimate?: number | null;
  revenue_reported?: number | null;
}

export interface MicroData {
  trailing_pe: number | null;
  forward_pe: number | null;
  peg_ratio: number | null;
  beta: number | null;
  dividend_yield: number | null;
  price_to_book: number | null;
  price_to_sales: number | null;
  enterprise_to_ebitda: number | null;
  enterprise_value: number | null;
  book_value: number | null;
  return_on_equity: number | null;
  return_on_assets: number | null;
  profit_margins: number | null;
  operating_margins: number | null;
  gross_margins: number | null;
  debt_to_equity: number | null;
  current_ratio: number | null;
  quick_ratio: number | null;
  revenue_growth: number | null;
  earnings_growth: number | null;
  free_cashflow: number | null;
  operating_cashflow: number | null;
  payout_ratio: number | null;
  held_percent_insiders: number | null;
  held_percent_institutions: number | null;
  fifty_two_week_change: number | null;
  sp500_fifty_two_week_change: number | null;
}

export interface InsiderTransaction {
  insider: string;
  position: string;
  transaction: string;
  date: string;
  shares: number | null;
  value: number | null;
}

export interface AnalystRating {
  period: string;
  strong_buy: number;
  buy: number;
  hold: number;
  sell: number;
  strong_sell: number;
}

export interface AnalystPriceTarget {
  current: number | null;
  low: number | null;
  mean: number | null;
  median: number | null;
  high: number | null;
}

export interface AnalystAction {
  date: string;
  firm: string;
  to_grade: string;
  from_grade: string;
  /** Rating-grade movement code: "main" | "up" | "down" | "init" | "reit" | other. */
  action: string;
  /** Per-analyst price target the firm assigned in this action.
   *  Optional — present only when yfinance exposes the price-target columns
   *  (recent versions). Older API responses leave it null and the UI
   *  shows a placeholder. */
  current_price_target?: number | null;
  /** Same firm's previous target. Pair with `current_price_target` to
   *  show "Raises 287→296" instead of just "Raises to 296". */
  prior_price_target?: number | null;
  /** Yahoo's labeled change: "Raises" | "Lowers" | "Maintains" | "Initiates".
   *  Distinct from `action` — a Maintain on the rating can pair with a
   *  target raise/lower. */
  price_target_action?: string | null;
}

export interface Fundamentals {
  ticker: string;
  annual: FundamentalsAnnual[];
  quarterly: FundamentalsQuarterly[];
  earnings: FundamentalsEarnings[];
  next_earnings_date: string | null;
  next_eps_estimate: number | null;
  /** Revenue forecast (analyst consensus) for the upcoming earnings event,
   *  when yfinance exposes it. NULL when the field isn't in the
   *  earnings_dates DataFrame (older yfinance versions or missing data). */
  next_revenue_estimate: number | null;
  micro: MicroData;
  insiders: InsiderTransaction[];
  analyst_ratings: AnalystRating[];
  analyst_actions: AnalystAction[];
  price_target: AnalystPriceTarget;
  error: string | null;
}

export interface LiveQuote {
  ticker: string;
  price: number | null;
  prev_close: number | null;
  change_abs: number | null;
  change_pct: number | null;
  day_open: number | null;
  day_high: number | null;
  day_low: number | null;
  volume: number | null;
  market_state: string | null;
  currency: string | null;
  fetched_at: number;
  error: string | null;
}

// === Stock scoring ===

export type RiskTier = "conservative" | "moderate" | "aggressive";

export type ScoreCategory =
  | "composite"
  | "quality"
  | "growth"
  | "value"
  | "momentum"
  | "sentiment";

export interface SubScores {
  quality: number | null;
  growth: number | null;
  value: number | null;
  momentum: number | null;
  sentiment: number | null;
}

/** One component inside a sub-score breakdown.
 *  `raw` is the input value from upstream (yfinance, technicals, ...);
 *  may be null when the data is missing. `points` ≤ `max`; the ratio
 *  drives the bar fill in the UI. */
export interface ScoreBreakdownComponent {
  raw: number | null;
  points: number;
  max: number;
}

/** Per-pillar breakdown — keys are component names (e.g. `roe`, `debt_equity`).
 *  Loose-typed because each pillar has its own component layout. The UI just
 *  iterates and renders bars, no static type needed. */
export type ScoreBreakdown = Record<
  string,
  Record<string, ScoreBreakdownComponent>
>;

export interface StockScore {
  stock_id: number;
  ticker: string;
  composite: number;
  sub_scores: SubScores;
  risk_tier: RiskTier;
  computed_at: string;
  breakdown: ScoreBreakdown;
}

export interface TopPickItem {
  stock_id: number;
  ticker: string;
  name: string;
  composite: number;
  risk_tier: RiskTier;
  sector: string | null;
  market_cap: number | null;
  change_pct: number | null;
}

export interface TopPicks {
  category: ScoreCategory;
  risk: RiskTier | null;
  items: TopPickItem[];
}
