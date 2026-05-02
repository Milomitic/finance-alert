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
  rule_kind: RuleKind | null;
  stock_id: number;
  ticker: string | null;
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
  progress_done: number;
  progress_total: number;
  stocks_scanned: number | null;
  stocks_skipped: number | null;
  alerts_fired: number | null;
  error_message: string | null;
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
  change_pct: number;
  last_close: number;
  prev_close: number | null;
}

export interface VolumeSpike extends Mover {
  vol_ratio: number;
}

export interface MoversBlock {
  gainers: Mover[];
  losers: Mover[];
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

export interface IndicatorSeries {
  sma50: IndicatorPoint[];
  sma200: IndicatorPoint[];
  rsi14: IndicatorPoint[];
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
