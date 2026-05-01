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

export type RuleKind = "rsi_oversold" | "rsi_overbought" | "golden_cross" | "death_cross";

export interface Rule {
  id: number;
  watchlist_id: number | null;
  kind: RuleKind;
  params: Record<string, unknown>;
  enabled: boolean;
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
