/* GENERATO — non modificare a mano.
 *
 * Tradotto dallo schema OpenAPI dell'app da
 *   backend/app/scripts/genera_tipi_frontend.py
 * e tenuto allineato da backend/tests/test_tipi_frontend.py, che fallisce se
 * questo file e' indietro rispetto ai modelli del server (FA-111).
 *
 * Niente `eslint-disable`: il file non viola nessuna regola, e una direttiva
 * che non sopprime niente e' un avviso del lint completo.
 */

export interface ActionAggregateOut {
  ticker: string;
  company_name?: string | null;
  institutional_slug: string;
  institutional_name: string;
  period_end_date: string;
  action: string;
  qoq_change_pct?: number | null;
  portfolio_pct?: number | null;
  value_usd?: number | null;
  stock_id?: number | null;
}

export interface AggregateStatsOut {
  most_picked: TickerAggregateOut[];
  recent_buys: ActionAggregateOut[];
  recent_sells: ActionAggregateOut[];
  sector_tilt: Record<string, number>;
}

export interface AlertFiringOut {
  name: string;
  severity?: string | null;
  since?: string | null;
  summary?: string | null;
  target?: string | null;
}

export interface AlertListOut {
  items: AlertOut[];
  total: number;
  has_more: boolean;
}

export interface AlertOut {
  id: number;
  rule_kind?: string | null;
  stock_id: number;
  ticker?: string | null;
  name?: string | null;
  triggered_at: string;
  signal_date?: string | null;
  trigger_price: number;
  currency?: string | null;
  snapshot: Record<string, unknown>;
  read_at: string | null;
  archived_at: string | null;
  same_day_same_tone?: number | null;
  same_day_same_tone_sector?: number | null;
  same_day_opposite_tone?: number | null;
  plan?: PlanBriefOut | null;
  outcome_hit?: boolean | null;
  outcome_fwd_return?: number | null;
  outcome_horizon_days?: number | null;
  outcome_mkt_excess?: number | null;
  outcome_entry_close?: number | null;
  next_earnings_date?: string | null;
  setup_origin?: AlertSetupOriginOut | null;
  rilevanza?: string | null;
  series_stalled?: boolean;
  series_last_bar?: string | null;
}

export interface AlertPatch {
  archived?: boolean | null;
}

export interface AlertPeerOut {
  alert_id: number;
  stock_id: number;
  ticker: string;
  name?: string | null;
  sector?: string | null;
}

export interface AlertSetupOriginOut {
  setup_id: number;
  detector: string;
  first_seen_at: string;
  lead_days?: number | null;
  converted_signal_date?: string | null;
}

export interface AlertsByDayPointOut {
  date: string;
  count: number;
  by_kind: Record<string, number>;
}

export interface AlertsByIndexPointOut {
  index_code: string;
  index_name: string;
  alert_count: number;
}

export interface AnalystPriceTargetOut {
  current: number | null;
  current_as_of?: string | null;
  low: number | null;
  mean: number | null;
  median: number | null;
  high: number | null;
}

export interface AnalystRatingOut {
  period: string;
  strong_buy: number;
  buy: number;
  hold: number;
  sell: number;
  strong_sell: number;
}

export interface ArretratoOut {
  conteggio: number;
  totale?: number | null;
  perche?: string;
}

export interface BulkAction {
  ids: number[];
  action: "archive" | "unarchive";
}

export interface BulkResult {
  affected: number;
}

export interface CacheKindStatOut {
  l1_entries: number;
  l2_entries: number;
  oldest_age_s: number | null;
  newest_age_s?: number | null;
  l2_oldest_age_s?: number | null;
  l2_newest_age_s?: number | null;
}

export interface CacheStatsOut {
  fundamentals: CacheKindStatOut;
  news: CacheKindStatOut;
  db: Record<string, unknown>;
  ohlcv?: OhlcvFreshnessOut;
}

export interface CalendarOut {
  from: string;
  to: string;
  events: (EarningsEventOut | MacroEventOut)[];
}

export interface CalibrationBucketOut {
  label: string;
  count: number;
  hit_rate: number | null;
  mean_pct: number | null;
  median_pct: number | null;
}

export interface CalibrationOut {
  days: number | null;
  window: number;
  total: number;
  by_confidence: CalibrationBucketOut[];
  by_nature: CalibrationBucketOut[];
  by_horizon: CalibrationBucketOut[];
  backtest_seed?: Record<string, unknown> | null;
}

export interface CatalogStatusOut {
  indices: IndexStatusOut[];
}

export interface CompanyProfileOut {
  long_business_summary?: string | null;
  website?: string | null;
  employees?: number | null;
  city?: string | null;
  country?: string | null;
  ceo?: string | null;
  founded?: number | null;
}

export interface ConfluenceComponentOut {
  alert_id: number;
  rule_kind: string;
  signal_name: string;
  strength: number;
  confidence: number;
  tone: string;
  horizon: string;
  signal_date?: string | null;
}

export interface ConfluenceOut {
  ticker: string;
  name?: string | null;
  direction: string;
  strength: number;
  n_signals: number;
  effective_n?: number;
  bull_strength: number;
  bear_strength: number;
  contested: boolean;
  multi_horizon: boolean;
  horizons: string[];
  components: ConfluenceComponentOut[];
}

export interface CountBucket {
  label: string;
  count: number;
}

export interface DashboardSummaryOut {
  kpis: KpiSummaryOut;
  alerts_by_day: AlertsByDayPointOut[];
  top_stocks_30d: TopStockOut[];
  alerts_by_index_30d: AlertsByIndexPointOut[];
  recent_alerts: AlertOut[];
  system_status: SystemStatusOut;
}

export interface DataHealthOut {
  ohlcv_age_days?: number | null;
  macro_age_days?: number | null;
  alert_age_days?: number | null;
  stale_ohlcv_stocks?: number | null;
  catalog_stocks?: number | null;
  setups_active?: number | null;
  setups_converted?: number | null;
  setups_expired?: number | null;
  api_keys?: Record<string, boolean>;
  basis_breaks?: number | null;
}

export interface DataSourceMetricOut {
  source: string;
  op: string;
  label: string;
  role: string;
  per_minute_limit: number | null;
  per_day_limit: number | null;
  notes: string;
  success: number;
  failure: number;
  success_rate: number;
  last_success_at: number | null;
  last_failure_at: number | null;
  last_failure_reason: string | null;
  health: string;
  calls_last_minute: number | null;
  calls_last_day: number | null;
  log_match?: string[];
}

export interface DegradedSourceOut {
  source: string;
  label: string;
  role: string;
  health: string;
}

export interface DeployHealthOut {
  git_sha?: string | null;
  uptime_seconds?: number | null;
  started_at?: string | null;
  apt_layer_built_at?: string | null;
  apt_security_date?: string | null;
  apt_age_days?: number | null;
  apt_stale?: boolean | null;
}

export interface DetectorPerfCellOut {
  key: string;
  n: number;
  abs_hit_rate: number;
  mkt_neutral_hit_rate: number | null;
  avg_fwd_return: number;
  low_confidence: boolean;
  effective_n?: number | null;
  horizon_days?: number | null;
  skill_ci_low?: number | null;
  skill_ci_high?: number | null;
  skill_verdict?: string | null;
}

export interface DetectorPerfMetaOut {
  total_rows: number;
  n_detectors: number;
  n_detectors_universe: number;
  date_min: string | null;
  date_max: string | null;
  min_n: number;
  computed_at: string;
  replay_available?: boolean;
  method_versions?: Record<string, number>;
}

export interface DetectorPerfRowOut {
  detector: string;
  total: DetectorPerfCellOut;
  by_regime: DetectorPerfCellOut[];
  by_tone: DetectorPerfCellOut[];
  by_strength: DetectorPerfCellOut[];
}

export interface DetectorPerformanceOut {
  meta: DetectorPerfMetaOut;
  overall?: DetectorPerfCellOut | null;
  detectors: DetectorPerfRowOut[];
  replay?: DetectorReplayOut | null;
}

export interface DetectorReplayOut {
  generated_at?: string | null;
  n_signals: number;
  date_min?: string | null;
  date_max?: string | null;
  params?: Record<string, unknown> | null;
  detectors: DetectorReplayRowOut[];
}

export interface DetectorReplayRowOut {
  detector: string;
  total: DetectorPerfCellOut;
  by_regime: DetectorPerfCellOut[];
  by_tone: DetectorPerfCellOut[];
  by_strength: DetectorPerfCellOut[];
}

export interface DigestResultOut {
  sent: boolean;
  alerts_count: number;
  reason: string | null;
}

export interface DrawingCreate {
  kind: string;
  price?: number | null;
  x1?: number | null;
  y1?: number | null;
  x2?: number | null;
  y2?: number | null;
}

export interface DrawingCreated {
  id: number;
  kind: string;
}

export interface EarningsEventOut {
  date: string;
  kind?: "earnings";
  ticker: string;
  name: string;
  eps_estimate?: number | null;
  revenue_estimate?: number | null;
  revenue_reported?: number | null;
  sector?: string | null;
  market_cap?: number | null;
  forward_pe?: number | null;
  earnings_growth?: number | null;
  composite_score?: number | null;
  risk_tier?: "conservative" | "moderate" | "aggressive" | null;
  earnings_when?: "pre" | "after" | null;
  eps_reported?: number | null;
  surprise_pct?: number | null;
}

export interface EffectiveRuleOut {
  kind: string;
  enabled: boolean;
  params: Record<string, unknown>;
  source?: string;
}

export interface EquityCurveOut {
  points: EquityPointOut[];
  n_signals: number;
  total_return_pct: number;
  mkt_neutral_return_pct: number;
  win_rate_pct: number;
  avg_return_pct: number;
  max_drawdown_pct: number;
  horizon_days: number;
  detectors: string[];
}

export interface EquityPointOut {
  date: string;
  equity: number;
  equity_mkt_neutral: number;
}

export interface EtfHoldingOut {
  symbol: string;
  name: string;
  weight: number;
  price?: number | null;
  change_pct?: number | null;
  currency?: string | null;
  sparkline?: number[];
  in_catalog?: boolean;
}

export interface EtfHoldingsOut {
  is_etf: boolean;
  holdings?: EtfHoldingOut[];
  weighted_change_pct?: number | null;
  underlying?: string | null;
}

export interface FilterOptionsOut {
  exchanges: string[];
  sectors: string[];
  industries: string[];
  countries: string[];
  indices: IndexOptionOut[];
}

export interface FundamentalsAnnualOut {
  fiscal_year_end: string;
  revenue: number | null;
  net_income: number | null;
  eps: number | null;
}

export interface FundamentalsEarningsOut {
  date: string;
  eps_estimate: number | null;
  eps_reported: number | null;
  surprise_pct: number | null;
  revenue_estimate?: number | null;
  revenue_reported?: number | null;
}

export interface FundamentalsOut {
  ticker: string;
  annual?: FundamentalsAnnualOut[];
  quarterly?: FundamentalsQuarterlyOut[];
  earnings?: FundamentalsEarningsOut[];
  next_earnings_date?: string | null;
  next_earnings_when?: "pre" | "after" | null;
  next_eps_estimate?: number | null;
  next_revenue_estimate?: number | null;
  curr_fy_eps_estimate?: number | null;
  curr_fy_revenue_estimate?: number | null;
  financial_currency?: string | null;
  micro?: MicroDataOut;
  profile?: CompanyProfileOut;
  insiders?: InsiderTransactionOut[];
  analyst_ratings?: AnalystRatingOut[];
  analyst_actions?: app__schemas__stock_detail__AnalystActionOut[];
  price_target?: AnalystPriceTargetOut;
  fetched_at?: number | null;
  error?: string | null;
}

export interface FundamentalsQuarterlyOut {
  fiscal_quarter_end: string;
  revenue: number | null;
  eps: number | null;
}

export interface GapSuggestionOut {
  op: string;
  why: string;
  suggestion: string;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

export interface HoldingDetailOut {
  ticker: string;
  company_name?: string | null;
  shares?: number | null;
  value_usd?: number | null;
  portfolio_pct?: number | null;
  qoq_change_pct?: number | null;
  qoq_change_shares?: number | null;
  action?: string | null;
  stock_id?: number | null;
  stock_country?: string | null;
  stock_sector?: string | null;
}

export interface HorizontalOut {
  id: number;
  price: number;
}

export interface IndexBreadthOut {
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
  top_gainers?: IndexMoverOut[];
  top_losers?: IndexMoverOut[];
}

export interface IndexMoverOut {
  ticker: string;
  name: string;
  change_pct: number;
}

export interface IndexOptionOut {
  code: string;
  name: string;
}

export interface IndexStatusOut {
  index_code: string;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_status: string | null;
  stocks_added: number | null;
  stocks_updated: number | null;
  stocks_removed: number | null;
  error_message: string | null;
}

export interface IndicatorBundleOut {
  ema20?: app__api__market_detail__IndicatorPointOut[];
  ema50?: app__api__market_detail__IndicatorPointOut[];
  ema200?: app__api__market_detail__IndicatorPointOut[];
  bb_upper?: app__api__market_detail__IndicatorPointOut[];
  bb_middle?: app__api__market_detail__IndicatorPointOut[];
  bb_lower?: app__api__market_detail__IndicatorPointOut[];
  rsi14?: app__api__market_detail__IndicatorPointOut[];
  macd_line?: app__api__market_detail__IndicatorPointOut[];
  macd_signal?: app__api__market_detail__IndicatorPointOut[];
  macd_hist?: app__api__market_detail__IndicatorPointOut[];
}

export interface IndicatorPeriodsOut {
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

export interface IndicatorSeriesOut {
  ema20?: app__schemas__stock_detail__IndicatorPointOut[];
  ema50: app__schemas__stock_detail__IndicatorPointOut[];
  ema200: app__schemas__stock_detail__IndicatorPointOut[];
  rsi14: app__schemas__stock_detail__IndicatorPointOut[];
  bb_upper?: app__schemas__stock_detail__IndicatorPointOut[];
  bb_middle?: app__schemas__stock_detail__IndicatorPointOut[];
  bb_lower?: app__schemas__stock_detail__IndicatorPointOut[];
  macd_line?: app__schemas__stock_detail__IndicatorPointOut[];
  macd_signal?: app__schemas__stock_detail__IndicatorPointOut[];
  macd_hist?: app__schemas__stock_detail__IndicatorPointOut[];
  periods?: IndicatorPeriodsOut;
}

export interface IndustryRow {
  name: string;
  sector: string | null;
  stock_count: number;
  avg_score: number | null;
}

export interface InfraComponentOut {
  job: string;
  namespace: string;
  up: boolean;
}

export interface InfraHealthOut {
  available: boolean;
  error?: string | null;
  prometheus_url?: string | null;
  targets_up?: number | null;
  targets_down?: number | null;
  down_targets?: TargetDownOut[];
  alerts_firing?: number | null;
  firing_alerts?: AlertFiringOut[];
  restarts_24h?: number | null;
  restart_details?: RestartDetailOut[];
  memory_pct?: number | null;
  cert_days?: number | null;
  argocd?: Record<string, unknown> | null;
  components?: InfraComponentOut[];
}

export interface InfraLogSourceOut {
  key: string;
  label: string;
  note: string;
}

export interface InfraLogsOut {
  source: string;
  reachable: boolean;
  records?: LogRecordOut[];
}

export interface InsiderTransactionOut {
  insider: string;
  position: string;
  transaction: string;
  date: string;
  shares: number | null;
  value: number | null;
}

export interface InstitutionalDetailOut {
  institutional: InstitutionalSummaryOut;
  holdings: HoldingDetailOut[];
  holdings_total?: number;
  composition?: HoldingDetailOut[];
  filed_date?: string | null;
  available_periods: string[];
}

export interface InstitutionalSummaryOut {
  id: number;
  slug: string;
  name: string;
  manager_name?: string | null;
  type: string;
  source: string;
  source_url?: string | null;
  description?: string | null;
  aum_usd?: number | null;
  latest_period_end?: string | null;
  total_value_usd?: number | null;
  total_positions?: number | null;
}

export interface KpiSummaryOut {
  alerts_last_24h: number;
  alerts_prev_24h: number;
  stocks_monitored: number;
  indices_count: number;
  last_scan: ScanStatusOut | null;
  next_scan_at: string | null;
  next_digest_at: string | null;
}

export interface LeaderRowOut {
  ticker: string;
  name?: string | null;
  sector?: string | null;
  quality?: number | null;
  technical?: number | null;
  value: number;
  detail?: string | null;
  signals_bull?: number;
  signals_bear?: number;
  detectors_bull?: number;
  analysts?: number | null;
  recommendation?: number | null;
  upside_pct?: number | null;
  target?: number | null;
  last_close?: number | null;
}

export interface LeaderboardsOut {
  analysts?: LeaderRowOut[];
  combined?: LeaderRowOut[];
  signals?: LeaderRowOut[];
  signal_window_days?: number;
}

export interface LiveAsset {
  symbol: string;
  name: string;
  category: string;
  flag?: string | null;
  quote?: app__schemas__stock_detail__LiveQuoteOut | null;
  history?: number[] | null;
  using_futures?: boolean;
  quote_symbol?: string;
  is_live?: boolean;
}

export interface LiveAssetsOut {
  assets: LiveAsset[];
}

export interface LiveMoverOut {
  ticker: string;
  name?: string | null;
  change_pct: number;
  price?: number | null;
  vol_today?: number | null;
  vol_ratio?: number | null;
  composite?: number | null;
  exchange?: string | null;
  as_of?: string | null;
}

export interface LiveMoversOut {
  gainers: LiveMoverOut[];
  losers: LiveMoverOut[];
  swept: number;
}

export interface LiveQuotesBatchOut {
  quotes: app__schemas__stock_detail__LiveQuoteOut[];
}

export interface LogRecordOut {
  ts: number;
  level: string;
  module: string;
  function: string;
  line: number;
  message: string;
  exception?: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface MacroEventOut {
  date: string;
  kind?: "macro";
  label: string;
  importance: "high" | "medium" | "low";
  region: "US" | "EU" | "EZ" | "UK" | "GB" | "JP" | "KR" | "CN" | "HK" | "CH" | "DE" | "FR" | "IT" | "ES" | "NL" | "BE" | "IE";
  series_id?: number | null;
  source?: string | null;
  currency?: string | null;
  prev_value?: number | null;
  prev_date?: string | null;
  prior_value?: number | null;
  prior_date?: string | null;
  change_pct?: number | null;
  unit?: string | null;
  history?: MacroObservationOut[];
  release_time?: string | null;
  expected_value?: number | null;
  actual_value?: number | null;
  surprise_pct?: number | null;
}

export interface MacroObservationOut {
  date: string;
  value: number | null;
}

export interface MacroReleaseOut {
  observation_period?: string | null;
  publication_date?: string | null;
  acquired_at?: string | null;
  period_label?: string | null;
  actual_value?: number | null;
  expected_value?: number | null;
  previous_value?: number | null;
  release_time_utc?: string | null;
}

export interface MacroSeriesDetailOut {
  series_id: number;
  fred_series_id: string;
  label: string;
  region: string;
  currency?: string | null;
  importance: "high" | "medium" | "low";
  value_kind?: string | null;
  source_scale?: string | null;
  description?: string | null;
  source?: string | null;
  data_acquired_at?: string | null;
  latest?: MacroReleaseOut | null;
  history?: MacroReleaseOut[];
  upcoming?: string[];
}

export interface MarketDetailOut {
  symbol: string;
  name: string;
  category: string;
  flag: string | null;
  range_key: string;
  last_close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  high_window: number | null;
  low_window: number | null;
  high_52w: number | null;
  low_52w: number | null;
  bars: app__api__market_detail__OhlcvBarOut[];
  indicators: IndicatorBundleOut;
  quote: app__api__market_detail__LiveQuoteOut | null;
}

export interface MarketGlobalOut {
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
  mood: string;
}

export interface MarketSummaryOut {
  available: boolean;
  is_stale?: boolean;
  reason?: string | null;
  computed_at?: string | null;
  scan_run_id?: number | null;
  global?: MarketGlobalOut | null;
  by_index?: IndexBreadthOut[];
  rsi_distribution?: RsiDistributionOut | null;
  sectors?: SectorBreadthOut[];
  movers?: MoversBlockOut | null;
  treemap?: TreemapLeafOut[];
}

export interface MeResponse {
  username: string;
}

export interface MicroDataOut {
  trailing_pe?: number | null;
  forward_pe?: number | null;
  peg_ratio?: number | null;
  trailing_peg_ratio?: number | null;
  price_to_book?: number | null;
  price_to_sales?: number | null;
  enterprise_to_ebitda?: number | null;
  enterprise_to_revenue?: number | null;
  enterprise_value?: number | null;
  book_value?: number | null;
  price_eps_current_year?: number | null;
  return_on_equity?: number | null;
  return_on_assets?: number | null;
  profit_margins?: number | null;
  operating_margins?: number | null;
  gross_margins?: number | null;
  ebitda_margins?: number | null;
  ebitda?: number | null;
  gross_profits?: number | null;
  net_income_to_common?: number | null;
  eps_trailing?: number | null;
  eps_forward?: number | null;
  eps_current_year?: number | null;
  earnings_quarterly_growth?: number | null;
  total_revenue?: number | null;
  revenue_per_share?: number | null;
  debt_to_equity?: number | null;
  current_ratio?: number | null;
  quick_ratio?: number | null;
  total_cash?: number | null;
  total_cash_per_share?: number | null;
  total_debt?: number | null;
  free_cashflow?: number | null;
  operating_cashflow?: number | null;
  revenue_growth?: number | null;
  earnings_growth?: number | null;
  revenue_quarterly_growth?: number | null;
  earnings_growth_5y?: number | null;
  revenue_growth_5y?: number | null;
  dividend_rate?: number | null;
  dividend_yield?: number | null;
  five_year_avg_dividend_yield?: number | null;
  trailing_annual_dividend_rate?: number | null;
  trailing_annual_dividend_yield?: number | null;
  payout_ratio?: number | null;
  beta?: number | null;
  shares_outstanding?: number | null;
  float_shares?: number | null;
  shares_short?: number | null;
  short_ratio?: number | null;
  short_percent_of_float?: number | null;
  held_percent_insiders?: number | null;
  held_percent_institutions?: number | null;
  recommendation_mean?: number | null;
  number_of_analyst_opinions?: number | null;
  fifty_two_week_change?: number | null;
  sp500_fifty_two_week_change?: number | null;
  audit_risk?: number | null;
  board_risk?: number | null;
  compensation_risk?: number | null;
  share_holder_rights_risk?: number | null;
  overall_risk?: number | null;
}

export interface MoverOut {
  ticker: string;
  name: string;
  index: string | null;
  sector: string | null;
  change_pct?: number | null;
  change_pct_5d?: number | null;
  change_pct_20d?: number | null;
  last_close: number;
  prev_close: number | null;
  sparkline?: number[];
  vol_today?: number | null;
  vol_ratio?: number | null;
  vol_5d?: number | null;
  vol_20d?: number | null;
  dollar_volume?: number | null;
  composite?: number | null;
  exchange?: string | null;
}

export interface MoversBlockOut {
  gainers: MoverOut[];
  losers: MoverOut[];
  gainers_5d?: MoverOut[];
  losers_5d?: MoverOut[];
  gainers_20d?: MoverOut[];
  losers_20d?: MoverOut[];
  volume_spikes: VolumeSpikeOut[];
  top_volume?: TopVolumeOut[];
  top_dollar_volume?: TopVolumeOut[];
  new_52w_high: MoverOut[];
  new_52w_low: MoverOut[];
  high_beta?: MoverOut[];
}

export interface MultiTfKpisOut {
  ticker: string;
  items: TimeframeKpisOut[];
}

export interface OhlcvFreshnessOut {
  max_date?: string | null;
  stocks_at_max?: number;
}

export interface PaginaIn {
  path: string;
  vista?: string | null;
}

export interface PhaseTimingOut {
  phase: string;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
}

export interface PillarAverages {
  profitability: number | null;
  sustainability: number | null;
  growth: number | null;
  value: number | null;
  momentum: number | null;
  sentiment: number | null;
}

export interface PlanBriefOut {
  esito: string;
  resolved_date: string;
  entry_date: string;
  entry: number;
  stop: number;
  tp1: number;
  tp2?: number | null;
  r: number;
  r_multiple: number;
  bars_to_outcome: number;
  horizon_days: number;
  mae_r: number;
  mfe_r: number;
  tp2_reached: boolean;
  stop_hit_date?: string | null;
  tp1_hit_date?: string | null;
  tp2_hit_date?: string | null;
}

export interface PlanCoverageOut {
  detector: string;
  alerts: number;
  with_plan: number;
  without_plan: number;
}

export interface PlanOnlyOpenOut {
  detector: string;
  open: number;
}

export interface PlanOutcomeListOut {
  items: PlanOutcomeRowOut[];
  total: number;
  has_more: boolean;
  counts_by_detector: Record<string, number>;
  summary?: PlanOutcomeSummaryOut | null;
  open_excluded?: number;
}

export interface PlanOutcomeRowOut {
  alert_id: number;
  ticker: string;
  name?: string | null;
  detector: string;
  tone: string;
  signal_date: string;
  entry_date: string;
  entry: number;
  stop: number;
  tp1: number;
  tp2?: number | null;
  r: number;
  horizon_days: number;
  esito: string;
  resolved_date: string;
  bars_to_outcome: number;
  r_multiple: number;
  mae_r: number;
  mfe_r: number;
  tp2_reached: boolean;
  stop_hit_date?: string | null;
  tp1_hit_date?: string | null;
  tp2_hit_date?: string | null;
}

export interface PlanOutcomeSummaryOut {
  n: number;
  effective_n: number;
  horizon_days: number;
  expectancy_r: number;
  expectancy_ci?: number[] | null;
  verdict: string;
  win_rate: number;
  esiti: Record<string, number>;
  stop_too_tight: number;
  mae_r_on_wins?: number | null;
  mfe_r_on_losses?: number | null;
  median_bars?: number | null;
  low_confidence: boolean;
  open_excluded?: number;
}

export interface PlanPerfMetaOut {
  rows: number;
  open_excluded?: number;
  only_open?: PlanOnlyOpenOut[];
  detectors_present: number;
  date_range: Record<string, string | null>;
  coverage: PlanCoverageOut[];
  min_n: number;
}

export interface PlanPerfRowOut {
  detector: string;
  n: number;
  effective_n: number;
  horizon_days: number;
  expectancy_r: number;
  expectancy_ci?: number[] | null;
  verdict: string;
  win_rate: number;
  esiti: Record<string, number>;
  stop_too_tight: number;
  mae_r_on_wins?: number | null;
  mfe_r_on_losses?: number | null;
  median_bars?: number | null;
  low_confidence: boolean;
  open_excluded?: number;
}

export interface PlanPerformanceOut {
  meta: PlanPerfMetaOut;
  rows: PlanPerfRowOut[];
}

export interface PlatformHealthOut {
  data_sources: DataSourceMetricOut[];
  yfinance_breaker: Record<string, unknown>;
  scheduler: SchedulerJobStatOut[];
  scans: RecentScanOut[];
  cache: CacheStatsOut;
  overall?: string;
  reasons?: string[];
  suggestions?: GapSuggestionOut[];
  data_health?: DataHealthOut | null;
  deploy?: DeployHealthOut | null;
  verification?: VerificationOut | null;
  uso_pagine?: UsoPagineOut | null;
}

export interface PositionCreate {
  ticker: string;
  side?: string;
  entry_price?: number | null;
  stop_price?: number | null;
  target_price?: number | null;
  size?: number | null;
  alert_id?: number | null;
  notes?: string | null;
}

export interface PositionOut {
  id: number;
  stock_id: number;
  ticker: string;
  name: string | null;
  alert_id: number | null;
  side: string;
  entry_price: number;
  stop_price: number | null;
  target_price: number | null;
  size: number | null;
  opened_at: string;
  closed_at: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  notes: string | null;
  last_price: number | null;
  price_source: string | null;
  unrealized_pct: number | null;
  unrealized_abs: number | null;
  realized_pct: number | null;
  realized_abs: number | null;
  currency?: string | null;
  unrealized_usd?: number | null;
  realized_usd?: number | null;
  cost_usd?: number | null;
}

export interface PositionUpdate {
  close?: boolean;
  exit_price?: number | null;
  stop_price?: number | null;
  target_price?: number | null;
  notes?: string | null;
}

export interface PreferitoOut {
  stock_id: number;
  ticker: string;
  name: string;
  exchange: string;
  currency?: string | null;
  instrument_type?: string | null;
  aggiunto_il: string;
}

export interface PremarketMoverOut {
  ticker: string;
  name?: string | null;
  price: number;
  prev_close: number;
  change_pct: number;
  volume?: number | null;
  instrument_type?: string | null;
}

export interface PremarketMoversOut {
  available: boolean;
  market_open: boolean;
  as_of?: string | null;
  computed_at?: string | null;
  refreshing?: boolean;
  progress_pct?: number;
  gainers?: PremarketMoverOut[];
  losers?: PremarketMoverOut[];
}

export interface PriceAlertCreate {
  target_price: number;
  direction: string;
  note?: string | null;
}

export interface PriceAlertOut {
  id: number;
  stock_id: number;
  target_price: number;
  direction: string;
  enabled: boolean;
  note: string | null;
  triggered_at: string | null;
  created_at: string;
}

export interface PriceAlertUpdate {
  enabled?: boolean | null;
  target_price?: number | null;
  direction?: string | null;
  note?: string | null;
}

export interface RecentScanOut {
  id: number;
  status: string;
  phase: string | null;
  trigger: string;
  started_at: string | null;
  completed_at: string | null;
  duration_s: number | null;
  progress_done: number | null;
  progress_total: number | null;
  alerts_count: number | null;
  error_message: string | null;
  stocks_scanned?: number | null;
  stocks_skipped?: number | null;
}

export interface RefreshAccepted {
  accepted?: boolean;
}

export interface RefreshRequest {
  index_code?: string | null;
}

export interface RestartDetailOut {
  pod: string;
  container: string;
  count: number;
  reason?: string | null;
}

export interface RsiDistributionOut {
  all: number[];
  by_index: Record<string, number[]>;
}

export interface ScanAccepted {
  accepted?: boolean;
}

export interface ScanLogOut {
  runs: ScanRunSummaryOut[];
}

export interface ScanRequest {
  stock_ids?: number[] | null;
}

export interface ScanRunSummaryOut {
  id: number;
  kind: string;
  trigger: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  total_duration_sec: number | null;
  progress_done: number;
  progress_total: number;
  stocks_scanned: number | null;
  stocks_skipped: number | null;
  alerts_fired: number | null;
  error_message: string | null;
  phases: PhaseTimingOut[];
}

export interface ScanStatusOut {
  is_running: boolean;
  last_run_id?: number | null;
  trigger?: string | null;
  status?: string | null;
  phase?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  last_progress_at?: string | null;
  progress_done?: number;
  progress_total?: number;
  stocks_scanned?: number | null;
  stocks_skipped?: number | null;
  alerts_fired?: number | null;
  current_target?: string | null;
  error_message?: string | null;
  is_stale?: boolean;
  seconds_since_last_progress?: number | null;
}

export interface ScanStopResult {
  stopped_run_id?: number | null;
  was_running: boolean;
  was_stale: boolean;
  message: string;
}

export interface SchedulerJobStatOut {
  job_id: string;
  last_run_at: number | null;
  last_result: string | null;
  last_duration_ms: number | null;
  last_error: string | null;
  runs: number;
  errors: number;
  next_run_time?: number | null;
  trigger?: string | null;
}

export interface ScoreHistoryOut {
  ticker: string;
  lens: "qualita" | "tecnico";
  points: ScoreHistoryPoint[];
}

export interface ScoreHistoryPoint {
  date: string;
  composite: number;
}

export interface SectorBreadthOut {
  sector: string;
  n_stocks: number;
  avg_change_pct: number;
  pct_above_ema200: number;
}

export interface SectorDetailOut {
  sector: string;
  kpis: SectorKpis;
  top_picks: SectorStockRow[];
  bottom_picks: SectorStockRow[];
  stocks: SectorStockRow[];
}

export interface SectorKpis {
  stock_count: number;
  avg_composite: number | null;
  median_composite: number | null;
  avg_technical?: number | null;
  technical_count?: number;
  median_pe: number | null;
  median_pb: number | null;
  median_roe: number | null;
  median_revenue_growth: number | null;
  median_profit_margin: number | null;
  median_dividend_yield: number | null;
  median_market_cap: number | null;
  score_distribution: number[];
  pillar_averages: PillarAverages;
  industry_breakdown: CountBucket[];
  country_distribution: CountBucket[];
  risk_distribution: CountBucket[];
  market_cap_distribution: CountBucket[];
}

export interface SectorStockRow {
  ticker: string;
  name: string | null;
  country: string | null;
  industry: string | null;
  market_cap: number | null;
  composite: number | null;
  quality: number | null;
  profitability: number | null;
  sustainability: number | null;
  growth: number | null;
  value: number | null;
  momentum: number | null;
  sentiment: number | null;
  risk_tier: string | null;
  pe: number | null;
  pb: number | null;
  roe: number | null;
  revenue_growth: number | null;
  profit_margin: number | null;
  dividend_yield: number | null;
}

export interface SectorSummary {
  name: string;
  stock_count: number;
  avg_score: number | null;
  median_pe: number | null;
  median_pb: number | null;
  median_roe: number | null;
  median_dividend_yield: number | null;
  avg_technical?: number | null;
  technical_count?: number;
  change_pct?: number | null;
  signals_7d?: number;
  signals_7d_bull?: number;
  signals_7d_bear?: number;
  etf_proxy?: string | null;
  score_trend?: SectorTrendPoint[];
}

export interface SectorTrendPoint {
  date: string;
  avg: number;
}

export interface SectorsOverviewOut {
  total_stocks: number;
  total_sectors: number;
  total_industries: number;
  sectors: SectorSummary[];
  industries: IndustryRow[];
}

export interface SetupListOut {
  setups: SetupOut[];
  total?: number;
  has_more?: boolean;
  counts_by_detector?: Record<string, number>;
  counts_by_condition?: Record<string, number>;
  stats: Record<string, unknown>;
}

export interface SetupOut {
  id: number;
  ticker: string;
  name?: string | null;
  currency?: string | null;
  detector: string;
  tone: string;
  proximity: number;
  distance_atr?: number | null;
  convenience: number;
  missing: string;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  annotations?: Record<string, unknown> | null;
  factors?: Record<string, number> | null;
  status?: string;
  closed_reason?: string | null;
  resolved_at?: string | null;
  lead_days?: number | null;
  converted_alert_id?: number | null;
  converted_signal_date?: string | null;
  converted_price?: number | null;
  conversion_source?: string | null;
  bar_lead_days?: number | null;
  outcome_signal_date?: string | null;
  outcome_horizon_days?: number | null;
  outcome_mkt_neutral_hit?: number | null;
  outcome_mkt_neutral_excess_pct?: number | null;
  pending_until?: string | null;
  next_earnings_date?: string | null;
}

export interface SignalDriftOut {
  summary: SignalDriftSummaryOut;
  detectors: SignalDriftRowOut[];
}

export interface SignalDriftRowOut {
  detector: string;
  n_matured: number;
  effective_n: number;
  recent_hit_rate: number;
  base_rate: number;
  delta: number;
  ci_low: number;
  ci_high: number;
  drift_flag: boolean;
  direction: string;
  horizon_days: number;
}

export interface SignalDriftSummaryOut {
  n_detectors: number;
  n_flagged: number;
  n_insufficient: number;
  n_decaying: number;
  n_improving: number;
  window_days: number;
  min_n: number;
  computed_at: string;
}

export interface SpotlightCardOut {
  type: "top_gainer" | "top_loser" | "most_alerted_7d" | "vol_spike";
  ticker: string;
  last_close?: number | null;
  sparkline?: number[];
  change_pct?: number | null;
  vol_ratio?: number | null;
  alerts_count?: number | null;
}

export interface SpotlightOut {
  cards: SpotlightCardOut[];
}

export interface StockDetailOut {
  stock: StockOut;
  ohlcv: app__schemas__stock_detail__OhlcvBarOut[];
  indicators: IndicatorSeriesOut;
  kpis: StockKpisOut;
  effective_rules: EffectiveRuleOut[];
  alerts_history: AlertOut[];
  exchange_tz?: string;
}

export interface StockDrawingsOut {
  horizontal: HorizontalOut[];
  trend: TrendOut[];
}

export interface StockKpisOut {
  last_close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  high_52w: number | null;
  low_52w: number | null;
  vol_avg_20: number | null;
  vol_today: number | null;
  vol_ratio: number | null;
}

export interface StockMetricsRefOut {
  last_close?: number | null;
  change_pct?: number | null;
  ema50?: number | null;
  ema200?: number | null;
  rsi14?: number | null;
  high_252?: number | null;
  low_252?: number | null;
  vol_ratio?: number | null;
  vol_today?: number | null;
  vol_avg_20?: number | null;
}

export interface StockNewsItemOut {
  title: string;
  link: string;
  publisher: string;
  published_at: string | null;
  sentiment?: "bullish" | "neutral" | "bearish";
}

export interface StockNewsOut {
  items: StockNewsItemOut[];
  fetched_at?: number | null;
}

export interface StockOut {
  id: number;
  ticker: string;
  exchange: string;
  name: string;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string | null;
  market_cap: number | null;
  instrument_type?: string;
  in_etfs?: string[];
  in_indices?: IndexOptionOut[];
  market_cap_usd: number | null;
}

export interface StockScoreOut {
  stock_id: number;
  ticker: string;
  composite: number;
  sub_scores: SubScoresOut;
  risk_tier: "conservative" | "moderate" | "aggressive";
  computed_at: string;
  breakdown: Record<string, unknown>;
  sector_avg?: number | null;
  sector_percentile?: number | null;
  universe_percentile?: number | null;
  peer_n?: number | null;
  quality_extras?: Record<string, unknown> | null;
}

export interface StockScoreRefOut {
  composite?: number | null;
  risk_tier?: "conservative" | "moderate" | "aggressive" | null;
  profitability?: number | null;
  sustainability?: number | null;
  growth?: number | null;
  value?: number | null;
  sentiment?: number | null;
  composite_delta_7d?: number | null;
}

export interface StockSearchItemOut {
  stock: StockOut;
  score: StockScoreRefOut;
  technical?: TechnicalScoreRefOut;
  metrics?: StockMetricsRefOut;
}

export interface StockSearchOut {
  items: StockSearchItemOut[];
  total: number;
  has_more: boolean;
  metrics_computed_at?: string | null;
}

export interface StockSignalScanOut {
  added: number;
  total: number;
}

export interface SubScoresOut {
  quality: number | null;
  profitability: number | null;
  sustainability: number | null;
  growth: number | null;
  value: number | null;
  momentum: number | null;
  sentiment: number | null;
}

export interface SystemStatusOut {
  scheduler_running: boolean;
  scan_alerts_next_run: string | null;
  send_digest_next_run: string | null;
  refresh_catalog_next_run: string | null;
  telegram_configured: boolean;
  last_digest_sent_at: string | null;
}

export interface TargetDownOut {
  job: string;
  namespace: string;
  instance?: string | null;
}

export interface TechnicalScoreOut {
  stock_id: number;
  ticker: string;
  composite: number;
  trend?: number | null;
  momentum?: number | null;
  structure?: number | null;
  volume?: number | null;
  rel_strength?: number | null;
  signals?: number | null;
  posture: string;
  computed_at: string;
  sector_rank?: number | null;
  sector_peers?: number | null;
}

export interface TechnicalScoreRefOut {
  composite?: number | null;
  trend?: number | null;
  momentum?: number | null;
  structure?: number | null;
  volume?: number | null;
  rel_strength?: number | null;
  signals?: number | null;
  posture?: string | null;
}

export interface TickerAggregateOut {
  ticker: string;
  company_name?: string | null;
  holder_count: number;
  total_value_usd: number;
  total_pct_sum: number;
  holders: string[];
  stock_id?: number | null;
  stock_country?: string | null;
  stock_sector?: string | null;
}

export interface TickerHolderOut {
  institutional_id: number;
  institutional_slug: string;
  institutional_name: string;
  institutional_manager?: string | null;
  institutional_type: string;
  period_end_date: string;
  shares?: number | null;
  value_usd?: number | null;
  portfolio_pct?: number | null;
  shares_change_pct?: number | null;
  portfolio_weight_delta_pp?: number | null;
  action?: string | null;
}

export interface TickerHoldersOut {
  ticker: string;
  holders: TickerHolderOut[];
  historical?: TickerHolderOut[];
}

export interface TimeframeKpisOut {
  timeframe: string;
  bars: number;
  last_close: number | null;
  rsi: number | null;
  rsi_tone: string;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  ema20_above: boolean | null;
  ema50_above: boolean | null;
  ema200_above: boolean | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  bb_position: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  macd_tone: string;
  composite_score: number;
  composite_label: string;
}

export interface TopPickItemOut {
  stock_id: number;
  ticker: string;
  name: string;
  composite: number;
  risk_tier: "conservative" | "moderate" | "aggressive";
  sector?: string | null;
  market_cap?: number | null;
  change_pct?: number | null;
}

export interface TopPicksOut {
  category: "composite" | "quality" | "profitability" | "sustainability" | "growth" | "value" | "sentiment";
  risk?: "conservative" | "moderate" | "aggressive" | null;
  items: TopPickItemOut[];
}

export interface TopStockOut {
  stock_id: number;
  ticker: string;
  name?: string | null;
  alert_count: number;
  top_kind: string | null;
}

export interface TopVolumeOut {
  ticker: string;
  name: string;
  index: string | null;
  sector: string | null;
  change_pct?: number | null;
  change_pct_5d?: number | null;
  change_pct_20d?: number | null;
  last_close: number;
  prev_close: number | null;
  sparkline?: number[];
  vol_today: number;
  vol_ratio?: number | null;
  vol_5d?: number | null;
  vol_20d?: number | null;
  dollar_volume?: number | null;
  composite?: number | null;
  exchange?: string | null;
}

export interface TreemapLeafOut {
  ticker: string;
  index: string | null;
  sector: string | null;
  market_cap: number;
  change_pct: number;
  last_close?: number | null;
  currency?: string | null;
  vol_today?: number | null;
}

export interface TrendOut {
  id: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface UsoPagineOut {
  dal?: string | null;
  oggi: string;
  rotte?: UsoRottaOut[];
}

export interface UsoRottaOut {
  rotta: string;
  ultimi_7: number;
  ultimi_30: number;
  ultimo_giorno: string;
}

export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export interface VerificationOut {
  codice_mai_eseguito?: ArretratoOut | null;
  violazioni_a11y?: ArretratoOut | null;
  mutanti_sopravvissuti?: ArretratoOut | null;
}

export interface VolumeSpikeOut {
  ticker: string;
  name: string;
  index: string | null;
  sector: string | null;
  change_pct?: number | null;
  change_pct_5d?: number | null;
  change_pct_20d?: number | null;
  last_close: number;
  prev_close: number | null;
  sparkline?: number[];
  vol_today?: number | null;
  vol_ratio: number;
  vol_5d?: number | null;
  vol_20d?: number | null;
  dollar_volume?: number | null;
  composite?: number | null;
  exchange?: string | null;
}

export interface WebVitalIn {
  metric: string;
  value: number;
  route?: string;
  device: string;
}

export interface app__api__market_detail__IndicatorPointOut {
  date: string;
  value: number | null;
}

export interface app__api__market_detail__LiveQuoteOut {
  price: number | null;
  prev_close: number | null;
  change_abs: number | null;
  change_pct: number | null;
  market_state: string | null;
  currency: string | null;
  error: string | null;
}

export interface app__api__market_detail__OhlcvBarOut {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface app__schemas__dashboard__AnalystActionOut {
  ticker: string;
  name?: string | null;
  date: string;
  firm: string;
  to_grade: string;
  from_grade: string;
  action: string;
  current_price_target?: number | null;
  prior_price_target?: number | null;
  price_target_action?: string | null;
  from_news?: boolean;
  current_price?: number | null;
}

export interface app__schemas__stock_detail__AnalystActionOut {
  date: string;
  firm: string;
  to_grade: string;
  from_grade: string;
  action: string;
  current_price_target?: number | null;
  prior_price_target?: number | null;
  price_target_action?: string | null;
  from_news?: boolean;
  source_link?: string | null;
  source_title?: string | null;
}

export interface app__schemas__stock_detail__IndicatorPointOut {
  date: string;
  value: number | null;
}

export interface app__schemas__stock_detail__LiveQuoteOut {
  ticker: string;
  price?: number | null;
  prev_close?: number | null;
  change_abs?: number | null;
  change_pct?: number | null;
  day_open?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  volume?: number | null;
  market_state?: string | null;
  currency?: string | null;
  fetched_at?: number;
  error?: string | null;
  as_of_date?: string | null;
}

export interface app__schemas__stock_detail__OhlcvBarOut {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
