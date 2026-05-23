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

/** A row in the screener result. Stock anagrafica plus a join to the
 *  composite score (when computed). Score is null for stocks the score
 *  service hasn't yet processed — the table renders "—" for those. */
export interface StockSearchItem {
  stock: Stock;
  score: {
    composite: number | null;
    risk_tier: "conservative" | "moderate" | "aggressive" | null;
    profitability: number | null;
    sustainability: number | null;
    growth: number | null;
    value: number | null;
    momentum: number | null;
    sentiment: number | null;
  };
}

export interface StockSearch {
  items: StockSearchItem[];
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
  industries: string[];
  countries: string[];
  indices: IndexOption[];
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

/** Signal-engine alerts use the "signal:<detector-name>" convention for
 *  rule_kind (e.g. "signal:volume_breakout"); they have rule_id === null. */
export type SignalKind = `signal:${string}`;

export interface Alert {
  id: number;
  rule_id: number | null;
  /** ISO date (YYYY-MM-DD) of the market-data bar where the rule's
   *  condition matched. May differ from `triggered_at` (the wall-clock
   *  moment the row was created): a scan run on Monday morning may detect
   *  a signal whose underlying bar closed Friday. NULL only for legacy
   *  rows from before this column existed. */
  signal_date?: string | null;
  rule_kind: SignalKind | string | null;
  stock_id: number;
  ticker: string | null;
  name: string | null;
  triggered_at: string;
  trigger_price: number;
  snapshot: Record<string, unknown>;
  read_at: string | null;
  archived_at: string | null;
}

export interface SignalChainStep {
  date: string;
  label: string;
  detail?: string;
  /** Present only on the non-technical (fundamental) leg of a hybrid signal.
   *  Values: "earnings" | "analyst" | "insider". Technical legs omit this key. */
  source?: string;
}

export interface SignalSnapshot {
  tone: "bull" | "bear";
  confidence: number; // 0..100
  chain: SignalChainStep[];
  factors?: Record<string, number>;
  invalidation?: { level?: number; reason?: string } | null;
  sources?: string[];
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
/** Backend emits one of these strings on the `phase` field while a job
 *  is running. Sub-phases are colon-delimited ("fetching:backfill") —
 *  the union below enumerates every value currently emitted but the type
 *  is `string` at runtime so the UI parses prefix-before-`:` when adding
 *  new sub-phases doesn't require a frontend redeploy in lockstep.
 *
 *  Bare values ("fetching", "evaluating") are kept for back-compat with
 *  rows written before sub-phases existed. */
export type ScanPhase =
  | "fetching"
  | "fetching:planning"
  | "fetching:backfill"
  | "fetching:incremental"
  | "evaluating"
  | "evaluating:loading_rules"
  | "evaluating:scoring"
  | "evaluating:persisting"
  | "sector_stats"
  | "scoring";

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
  /** "What we're touching right now" — a ticker, optionally annotated
   *  ("AAPL · chunk 3/12"). NULL when the phase has no per-item focus
   *  (start/end bookends, or terminal states). Rendered as a small chip
   *  under the phase label in RunProgressToast. */
  current_target: string | null;
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

export interface AlertsByIndexPoint {
  index_code: string;
  index_name: string;
  alert_count: number;
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
  alerts_by_index_30d: AlertsByIndexPoint[];
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
  pct_above_ema200: number;
  pct_above_ema50: number;
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
  pct_above_ema200: number | null;
  pct_above_ema50: number | null;
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
  pct_above_ema200: number;
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
  /** Absolute share count traded today. Used by the "Top movers" card
   *  to surface volume next to the % change. Optional — older snapshot
   *  payloads predate this field. */
  vol_today?: number | null;
  /** vol_today / vol_avg_20 — multiplier vs the 20-day average. Tells
   *  the reader whether today's volume is unusual. Same value as on
   *  `VolumeSpike` / `TopVolume`. Optional. */
  vol_ratio?: number | null;
  /** USD notional turnover (vol_today × USD price). Powers the volume
   *  card's "Controvalore" view. Optional — older snapshots lack it. */
  dollar_volume?: number | null;
  /** Latest persisted composite score (0-100). Optional — null when
   *  the score service hasn't yet processed the stock. */
  composite?: number | null;
}

export interface VolumeSpike extends Mover {
  vol_ratio: number;
}

export interface TopVolume extends Mover {
  /** Absolute share count traded today (raw count, not millions). */
  vol_today: number;
  /** vol_today / vol_avg_20 — kept alongside the absolute count so the
   *  card can show both "X shares" + "Y× normal" context. */
  vol_ratio?: number | null;
  /** Latest persisted composite score (0-100) — None when not yet
   *  recomputed for the stock. Surfaced as the right-most chip on the
   *  dashboard's "Volumi maggiori" row. */
  composite?: number | null;
}

export interface MoversBlock {
  gainers: Mover[];
  losers: Mover[];
  gainers_5d?: Mover[];
  losers_5d?: Mover[];
  gainers_20d?: Mover[];
  losers_20d?: Mover[];
  volume_spikes: VolumeSpike[];
  /** Optional — older market_snapshot rows didn't include this list.
   *  Falls back to empty when missing. */
  top_volume?: TopVolume[];
  /** Same rows as top_volume but ranked by USD notional turnover. The
   *  volume card toggles between share-count and this. Optional. */
  top_dollar_volume?: TopVolume[];
  new_52w_high: Mover[];
  new_52w_low: Mover[];
  /** Leveraged-bull ETFs (SOXL/TNA…) + highest-volatility names. Folded
   *  into the Top-movers card's 15s live-polling + intraday display
   *  pools so these high-beta names surface intraday. Optional — older
   *  snapshots predate it. */
  high_beta?: Mover[];
}

export interface TreemapLeaf {
  ticker: string;
  index: string | null;
  sector: string | null;
  market_cap: number;
  change_pct: number;
  /** Listing-currency last close. Null when the snapshot is from an
   *  older schema version (pre-Phase 3D). */
  last_close?: number | null;
  /** ISO-3 currency, e.g. "USD"/"EUR"/"HKD". Used by the screener's
   *  Prezzo column to format the close with the right symbol. */
  currency?: string | null;
  /** Volume on the day the snapshot was taken. */
  vol_today?: number | null;
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
 *  range. The series-key names (ema20/ema50/ema200, rsi14) are SLOT names —
 *  the real periods adapt per range. The UI reads this to label toggles
 *  with the actual values used (e.g. "SMA 10" on a 1m chart). */
export interface IndicatorPeriods {
  ema_fast: number;
  ema_mid: number;
  ema_slow: number;
  rsi: number;
  bb_period: number;
  bb_k: number;
  macd_fast: number;
  macd_slow: number;
  macd_signal: number;
}

export interface IndicatorSeries {
  ema20?: IndicatorPoint[];
  ema50: IndicatorPoint[];
  ema200: IndicatorPoint[];
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
  /** Always "tier1" after watchlists were removed. Field kept for
   *  forward-compat with any new override mechanism. */
  source: "tier1";
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
  /** Server-classified headline sentiment via the finance-keyword
   *  scorer in `backend/app/services/news_sentiment.py`. The
   *  classifier biases toward "neutral" — only emits "bullish" /
   *  "bearish" when there's a decisive signal in the title. Defaults
   *  to "neutral" for cached pre-sentiment items so the field is
   *  always present on read. */
  sentiment?: "bullish" | "neutral" | "bearish";
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
  // Valuation multiples
  trailing_pe: number | null;
  forward_pe: number | null;
  peg_ratio: number | null;
  trailing_peg_ratio?: number | null;
  price_to_book: number | null;
  price_to_sales: number | null;
  enterprise_to_ebitda: number | null;
  enterprise_to_revenue?: number | null;
  enterprise_value: number | null;
  book_value: number | null;
  price_eps_current_year?: number | null;
  // Profitability / margins
  return_on_equity: number | null;
  return_on_assets: number | null;
  profit_margins: number | null;
  operating_margins: number | null;
  gross_margins: number | null;
  ebitda_margins?: number | null;
  ebitda?: number | null;
  gross_profits?: number | null;
  net_income_to_common?: number | null;
  // Earnings / EPS
  eps_trailing?: number | null;
  eps_forward?: number | null;
  eps_current_year?: number | null;
  earnings_quarterly_growth?: number | null;
  // Revenue
  total_revenue?: number | null;
  revenue_per_share?: number | null;
  // Leverage / liquidity
  debt_to_equity: number | null;
  current_ratio: number | null;
  quick_ratio: number | null;
  total_cash?: number | null;
  total_cash_per_share?: number | null;
  total_debt?: number | null;
  // Cash flow
  free_cashflow: number | null;
  operating_cashflow: number | null;
  // Growth
  revenue_growth: number | null;
  earnings_growth: number | null;
  revenue_quarterly_growth?: number | null;
  earnings_growth_5y?: number | null;
  revenue_growth_5y?: number | null;
  // Dividend
  dividend_rate?: number | null;
  dividend_yield: number | null;
  five_year_avg_dividend_yield?: number | null;
  trailing_annual_dividend_rate?: number | null;
  trailing_annual_dividend_yield?: number | null;
  payout_ratio: number | null;
  // Beta / risk
  beta: number | null;
  // Shares / float / short interest
  shares_outstanding?: number | null;
  float_shares?: number | null;
  shares_short?: number | null;
  short_ratio?: number | null;
  short_percent_of_float?: number | null;
  // Holdings
  held_percent_insiders: number | null;
  held_percent_institutions: number | null;
  // Analyst aggregate
  recommendation_mean?: number | null;
  number_of_analyst_opinions?: number | null;
  // Performance vs market
  fifty_two_week_change: number | null;
  sp500_fifty_two_week_change: number | null;
  // Governance / risk scores (Yahoo's 1-10)
  audit_risk?: number | null;
  board_risk?: number | null;
  compensation_risk?: number | null;
  share_holder_rights_risk?: number | null;
  overall_risk?: number | null;
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
  /** True when this row was extracted from a news headline (regex parse)
   *  rather than yfinance's structured upgrades_downgrades table. Drives
   *  the "from news" badge + click-through link in the UI. */
  from_news?: boolean;
  /** When `from_news`, the article URL the user clicks through to. */
  source_link?: string | null;
  /** When `from_news`, the original headline (rendered as hover-title). */
  source_title?: string | null;
}

/** Identity / "anagrafica" data extracted from yfinance Ticker.info.
 *  All fields optional — the UI gracefully hides what's missing rather
 *  than rendering placeholder rows. Returned on the new
 *  CompanyOverviewCard. */
export interface CompanyProfile {
  long_business_summary: string | null;
  website: string | null;
  employees: number | null;
  city: string | null;
  country: string | null;
  ceo: string | null;
  founded: number | null;
}

export interface Fundamentals {
  ticker: string;
  annual: FundamentalsAnnual[];
  quarterly: FundamentalsQuarterly[];
  earnings: FundamentalsEarnings[];
  next_earnings_date: string | null;
  /** When the next earnings is released relative to the session.
   *  "pre"   -> render sun glyph;
   *  "after" -> moon glyph;
   *  null    -> no glyph.
   *  Computed server-side from yfinance UTC time + listing country.
   *  Currently populated only for US stocks; non-US returns null. */
  next_earnings_when?: "pre" | "after" | null;
  next_eps_estimate: number | null;
  /** Revenue forecast (analyst consensus) for the upcoming earnings event,
   *  when yfinance exposes it. NULL when the field isn't in the
   *  earnings_dates DataFrame (older yfinance versions or missing data). */
  next_revenue_estimate: number | null;
  micro: MicroData;
  /** Optional for back-compat with cached pre-V2 API responses. */
  profile?: CompanyProfile;
  insiders: InsiderTransaction[];
  analyst_ratings: AnalystRating[];
  analyst_actions: AnalystAction[];
  price_target: AnalystPriceTarget;
  error: string | null;
}

/** One ETF component holding, enriched with live price + day variation
 *  + a short OHLCV sparkline. Powers the stock-detail "Componenti ETF"
 *  view. */
export interface EtfHolding {
  symbol: string;
  name: string;
  weight: number;             // fraction 0..1 of the fund
  price: number | null;
  change_pct: number | null;  // daily
  currency: string | null;
  sparkline: number[];        // last ~30 closes (catalog holdings only)
  in_catalog: boolean;
}

export interface EtfHoldings {
  is_etf: boolean;
  holdings: EtfHolding[];
  /** Weighted average of the components' day variation — proxy for the
   *  underlying index's move. Null when no component has a quote. */
  weighted_change_pct: number | null;
  /** For a leveraged/inverse ETF: the physical ETF whose basket is shown
   *  in place of the swaps (e.g. SOXL → "SOXX"). Null for plain ETFs. */
  underlying?: string | null;
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
  /** ISO date (YYYY-MM-DD) the `price` refers to. The chart overlays a
   *  "today" candle when this equals today, even at market CLOSED
   *  (provisional/official today close before the EOD scan). */
  as_of_date?: string | null;
}

// === Stock scoring ===

export type RiskTier = "conservative" | "moderate" | "aggressive";

export type ScoreCategory =
  | "composite"
  | "quality"        // legacy V3.1 alias = avg(profitability, sustainability)
  | "profitability"
  | "sustainability"
  | "growth"
  | "value"
  | "momentum"
  | "sentiment";

export interface SubScores {
  /** Legacy V3.1 alias; = avg(profitability, sustainability) on the
   *  backend so old screener queries keep working. New UI surfaces
   *  should read profitability + sustainability directly. */
  quality: number | null;
  profitability: number | null;
  sustainability: number | null;
  growth: number | null;
  value: number | null;
  momentum: number | null;
  sentiment: number | null;
}

/** One component inside a sub-score breakdown (score engine v2 shape).
 *
 *  `raw` is the input value from upstream (yfinance, technicals, news,
 *  analyst data, …); null when the data is missing. `score` is the
 *  component's normalized contribution in [0, 100], or null when the
 *  raw input wasn't available. `weight` is the relative weight of the
 *  component within its pillar (the aggregator computes
 *  `pillar = Σ score·weight / Σ weight` over the *present* components
 *  only — missing ones contribute to NEITHER numerator nor denominator).
 *  `present` is the redundant boolean flag for fast UI checks.
 */
export interface ScoreBreakdownComponent {
  raw: number | string | null;
  score: number | null;
  weight: number;
  present: boolean;
  /** Sector peer median used by the sector-aware blended scoring
   *  (V3.1+). Null when no benchmark was available — the lane fell
   *  back to pure absolute scoring. The UI can surface this as
   *  "vs peer median 19.6%" tooltip without altering the main raw
   *  value display. */
  sector_median?: number | null;
}

/** Optional per-pillar meta entry (key `_meta`). Carries the
 *  active-component count + the sum of weights actually contributing,
 *  so the UI can show "8 di 12 componenti attivi · pesi rinormalizzati"
 *  in the breakdown tooltip. */
export interface ScoreBreakdownMeta {
  components_present: number;
  components_total: number;
  weight_sum_present: number;
}

/** Per-pillar breakdown — keys are component names plus the optional
 *  `_meta`. Each pillar dict has the meta in addition to the components,
 *  so the consumer must filter `_meta` out when iterating components. */
export type ScoreBreakdown = Record<
  string,
  Record<string, ScoreBreakdownComponent | ScoreBreakdownMeta>
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

// === Economic calendar ===

/** Macro-event importance tier. Drives chip color and the importance filter
 *  pill set on the calendar page. Mirrors the backend Pydantic schema. */
export type MacroImportance = "high" | "medium" | "low";

export interface EarningsEvent {
  /** ISO YYYY-MM-DD — the trading day of the release. */
  date: string;
  /** Discriminator. */
  kind: "earnings";
  ticker: string;
  name: string;
  eps_estimate: number | null;
  revenue_estimate: number | null;
  sector: string | null;
  market_cap: number | null;
  // Extras used by the right-pane stock list (split-view detail panel).
  // Optional — older API responses (pre-calendar-UX-rework) won't have them.
  forward_pe?: number | null;
  earnings_growth?: number | null;       // YoY EPS growth, fraction (0.27 = 27%)
  composite_score?: number | null;       // 0-100
  risk_tier?: "conservative" | "moderate" | "aggressive" | null;
  /** Inferred release timing relative to the trading session:
   *   - "pre"   → before market open (the day-icon ☀ goes BEFORE the close)
   *   - "after" → after market close (☾ moon icon)
   *   - null    → no signal available
   *  Inferred from yfinance earnings_dates timestamp UTC hour vs
   *  the typical US session (US: pre = before 14:00 UTC, after = on/after 20:00). */
  earnings_when?: "pre" | "after" | null;
  /** Phase 3G: actual EPS reported. Null for upcoming quarters. */
  eps_reported?: number | null;
  /** Surprise = (reported - estimate) / |estimate| * 100. Null when
   *  the quarter hasn't reported yet or estimate was missing. */
  surprise_pct?: number | null;
}

export interface MacroObservationPoint {
  /** ISO date of the reference period (e.g. "2026-04-01" for April CPI). */
  date: string;
  /** FRED-reported value. NULL when missing/withheld. */
  value: number | null;
}

export interface MacroEvent {
  date: string;
  kind: "macro";
  /** Human-readable label, e.g. "FOMC rate decision", "US CPI release". */
  label: string;
  importance: MacroImportance;
  /** Two-letter region code: "US" | "EU" | "UK" | "JP" | etc. */
  region: string;
  /** FRED-driven insight fields. Populated when the event came from
   *  the macro_release_dates + macro_observations join; null when
   *  it's from the hardcoded fallback list. The UI shows the prev /
   *  change / sparkline only when present. */
  prev_value?: number | null;
  /** ISO date of the most-recent prior reading (when the indicator
   *  last published). Lets the UI render "Precedente: 3.2% (1 mar 2026)"
   *  so the user knows which period the prev value covers. */
  prev_date?: string | null;
  prior_value?: number | null;
  prior_date?: string | null;
  change_pct?: number | null;
  unit?: string | null;
  history?: MacroObservationPoint[];
  /** UTC HH:MM of the scheduled release ("12:30" = 8:30 ET). */
  release_time?: string | null;
  /** Phase 3G: median analyst forecast for this release, sourced from
   *  Forexfactory's free weekly XML feed. Null when the event isn't in
   *  the consensus mapping or the forecast hasn't yet been published. */
  expected_value?: number | null;
  /** Post-release actual, also from Forexfactory. Often arrives faster
   *  than FRED's official observation update — use this to show the
   *  number on the calendar moments after release. */
  actual_value?: number | null;
  /** Surprise = (actual - expected) / |expected| * 100. Null when either
   *  side is missing or expected is zero (rare). */
  surprise_pct?: number | null;
  /** Stable id of the underlying MacroSeries — drives the deep-link from
   *  a calendar chip to /macro/:series_id. Null for events without a
   *  backing series row (hardcoded fallback list); the "Apri dettaglio"
   *  link stays hidden in that case. */
  series_id?: number | null;
  /** Publishing organization — "Fonte: …" line in the detail header. */
  source?: string | null;
  /** ISO 4217 currency derived from `region` (US→USD, EZ→EUR, ...). */
  currency?: string | null;
}

/** One historical release row, returned by `/api/macro/{series_id}`.
 *  Used by the detail page's bar chart + history table. */
export interface MacroRelease {
  release_date: string;
  /** Italian short-month label of the period the release refers to —
   *  "Apr", "Mag", "Set". Mirrors the "(Apr)" suffix Investing shows. */
  period_label?: string | null;
  actual_value?: number | null;
  /** Null on historical rows: we don't backfill consensus (Forexfactory's
   *  free feed is week-of only). */
  expected_value?: number | null;
  /** Value of the immediately-prior release — pre-computed by the
   *  endpoint so the table doesn't need a second pass. */
  previous_value?: number | null;
  release_time_utc?: string | null;
}

/** Full payload of `/api/macro/{series_id}`. The detail page renders
 *  everything from a single fetch. */
export interface MacroSeriesDetail {
  series_id: number;
  fred_series_id: string;
  label: string;
  region: string;
  currency?: string | null;
  importance: MacroImportance;
  unit?: string | null;
  description?: string | null;
  source?: string | null;
  last_refreshed_at?: string | null;
  /** Most-recent release with previous_value pointing at the one before. */
  latest?: MacroRelease | null;
  /** Newest → oldest. The chart reverses for left-to-right rendering. */
  history: MacroRelease[];
  /** Future scheduled publications (date only). */
  upcoming: string[];
}

/** Discriminated union over the `kind` tag — narrowing on `kind` gives full
 *  field type safety in components without runtime checks. */
export type CalendarEvent = EarningsEvent | MacroEvent;

export interface Calendar {
  /** ISO date — start of the requested range (inclusive). */
  from: string;
  /** ISO date — end of the requested range (inclusive). */
  to: string;
  /** Sorted ascending by date, then earnings-first within a date, then
   *  macros by descending importance (per backend contract). */
  events: CalendarEvent[];
}

// ---------------------------------------------------------------------------
// Institutional / superinvestor portfolios
// ---------------------------------------------------------------------------

/** Open string — backend uses "superinvestor" | "institutional" | "hedge_fund"
 *  but Phase 2/3 sources may add more, and the UI doesn't care. */
export type InstitutionalType = string;

export interface InstitutionalSummary {
  id: number;
  slug: string;
  name: string;
  manager_name: string | null;
  type: InstitutionalType;
  source: string;
  source_url: string | null;
  description: string | null;
  aum_usd: number | null;
  /** ISO date — null if no filing yet. */
  latest_period_end: string | null;
  total_value_usd: number | null;
  total_positions: number | null;
}

export interface HoldingDetail {
  ticker: string;
  company_name: string | null;
  shares: number | null;
  value_usd: number | null;
  portfolio_pct: number | null;
  qoq_change_pct: number | null;
  qoq_change_shares: number | null;
  /** "new" | "add" | "reduce" | "sold_out" | "hold" — kept open for forward-compat. */
  action: string | null;
  /** Catalog enrichment: present when ticker matches a row in `stocks`. */
  stock_id: number | null;
  stock_country: string | null;
  stock_sector: string | null;
}

export interface InstitutionalDetail {
  institutional: InstitutionalSummary;
  holdings: HoldingDetail[];
  filed_date: string | null;
  /** All quarter-end dates for which we have a snapshot, newest first. */
  available_periods: string[];
}

export interface TickerAggregate {
  ticker: string;
  company_name: string | null;
  /** How many tracked institutionals hold this ticker in their latest filing. */
  holder_count: number;
  total_value_usd: number;
  /** Sum of portfolio_pct across holders — proxy for collective conviction. */
  total_pct_sum: number;
  /** Up to 5 holder names for display. */
  holders: string[];
  stock_id: number | null;
  stock_country: string | null;
  stock_sector: string | null;
}

export interface ActionAggregate {
  ticker: string;
  company_name: string | null;
  institutional_slug: string;
  institutional_name: string;
  period_end_date: string;
  action: string;
  qoq_change_pct: number | null;
  portfolio_pct: number | null;
  /** Position value at the filing's report date — absolute $ context
   *  for the +/- % delta. Null when the filing didn't expose it. */
  value_usd: number | null;
  /** Catalog hit (drives ticker linking + StockLogo CDN lookup). */
  stock_id: number | null;
}

export interface AggregateStats {
  most_picked: TickerAggregate[];
  recent_buys: ActionAggregate[];
  recent_sells: ActionAggregate[];
  /** Sector -> total $ across latest filings. Sorted descending in the
   *  backend response. */
  sector_tilt: Record<string, number>;
}

export interface TickerHolder {
  institutional_id: number;
  institutional_slug: string;
  institutional_name: string;
  institutional_manager: string | null;
  institutional_type: InstitutionalType;
  period_end_date: string;
  shares: number | null;
  value_usd: number | null;
  portfolio_pct: number | null;
  qoq_change_pct: number | null;
  action: string | null;
}

export interface TickerHolders {
  ticker: string;
  holders: TickerHolder[];
  /** Funds that USED to hold the ticker but are no longer current
   *  holders (sold out / stale). Each row is their most recent
   *  holding. Only populated when fetched with include_historical. */
  historical?: TickerHolder[];
}
