/**
 * Typed REST + SSE client for /api/platform/*.
 * Mirrors the Pydantic shapes in backend/app/schemas/platform.py.
 */
export type DataSourceMetric = {
  source: string;
  op: string;
  label: string;
  role: "primary" | "fallback" | "scheduled" | string;
  per_minute_limit: number | null;
  per_day_limit: number | null;
  notes: string;
  success: number;
  failure: number;
  success_rate: number; // -1 when idle
  last_success_at: number | null;
  last_failure_at: number | null;
  last_failure_reason: string | null;
  /** "unavailable" = plan-gated (tutti i fallimenti HTTP 403): slate,
   *  esclusa dalla derivazione del banner degradato.
   *  "stale" = nessun successo entro la cadenza attesa della fonte
   *  (cron/probe morto con contatori congelati sul verde). */
  health: "healthy" | "degraded" | "failing" | "unavailable" | "idle" | "stale" | string;
  calls_last_minute: number | null;
  calls_last_day: number | null;
  /** Lowercase substrings that identify this source's log lines (module or
   *  message). Used to filter the live-log table when a source is clicked.
   *  Optional for back-compat with older API responses. */
  log_match?: string[];
};

export type SchedulerJobStat = {
  job_id: string;
  last_run_at: number | null;
  last_result: string | null;
  last_duration_ms: number | null;
  last_error: string | null;
  runs: number;
  errors: number;
  /** Prossima esecuzione pianificata (epoch s). Assente/null sui payload
   *  vecchi o quando il job non è più registrato. */
  next_run_time?: number | null;
  /** Repr del trigger APScheduler, es. "cron[hour='23', minute='30']". */
  trigger?: string | null;
};

export type RecentScan = {
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
};

export type CacheKindStat = {
  l1_entries: number;
  l2_entries: number;
  // L1 (in-process) freshness — resets on restart.
  oldest_age_s: number | null;
  newest_age_s: number | null;
  // L2 (persisted fetch_cache) freshness — survives restarts.
  l2_oldest_age_s: number | null;
  l2_newest_age_s: number | null;
};

/** Hint di gap-analysis: un'operazione con TUTTE le fonti in errore/degradate
 *  + il suggerimento di fallback. Prima viveva sul (rimosso) endpoint
 *  /api/health/data-sources; ora viaggia dentro il payload piattaforma. */
export type GapSuggestion = {
  op: string;
  why: string;
  suggestion: string;
};

/** Freschezza e inventario dei dati su cui gira l'app. */
export type DataHealth = {
  ohlcv_age_days: number | null;
  macro_age_days: number | null;
  alert_age_days: number | null;
  stale_ohlcv_stocks: number | null;
  catalog_stocks: number | null;
  setups_active: number | null;
  setups_converted: number | null;
  setups_expired: number | null;
  api_keys: Record<string, boolean>;
  basis_breaks: number | null;
};

/** Cosa sta girando adesso: l'unica risposta diretta a "la mia modifica e' a
 *  schermo". CI verde e ArgoCD Synced non la danno — il bump del tag immagine
 *  e' un commit successivo, quindi esiste sempre una finestra in cui tutto e'
 *  verde e il pod esegue l'immagine precedente. */
export type DeployHealth = {
  git_sha: string | null;
  uptime_seconds: number | null;
  started_at: string | null;
};

export type PlatformHealth = {
  data_sources: DataSourceMetric[];
  yfinance_breaker: Record<string, unknown>;
  scheduler: SchedulerJobStat[];
  scans: RecentScan[];
  cache: {
    fundamentals: CacheKindStat;
    news: CacheKindStat;
    db: { size_mb: number };
    /** Freschezza dell'OHLCV memorizzato (quello che leggono gli scan):
     *  data dell'ultima barra + titoli con barra a quella data. Opzionale
     *  per retro-compatibilità con payload vecchi. */
    ohlcv?: { max_date: string | null; stocks_at_max: number };
  };
  /** Rollup calcolato server-side (health_rollup.compute_rollup). Opzionale
   *  per retro-compatibilità: sui payload vecchi il banner ricade sulla
   *  derivazione client. */
  overall?: "operational" | "degraded" | "outage" | string;
  reasons?: string[];
  /** Hint gap-analysis — vuoto quando ogni operazione ha ≥1 fonte sana. */
  suggestions?: GapSuggestion[];
  data_health?: DataHealth | null;
  deploy?: DeployHealth | null;
};

export type LogRecord = {
  ts: number;
  level: string;
  module: string;
  function: string;
  line: number;
  message: string;
  exception: string | null;
};

export async function fetchHealth(): Promise<PlatformHealth> {
  const r = await fetch("/api/platform/health", { credentials: "include" });
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

/** One detector's drift verdict (realised recent hit-rate vs calibrated base). */
export type SignalDriftRow = {
  detector: string;
  n_matured: number;
  recent_hit_rate: number;
  base_rate: number;
  delta: number;
  ci_low: number;
  ci_high: number;
  drift_flag: boolean;
};

export async function fetchSignalDrift(): Promise<{ detectors: SignalDriftRow[] }> {
  const r = await fetch("/api/platform/signal-drift", { credentials: "include" });
  if (!r.ok) throw new Error(`signal-drift ${r.status}`);
  return r.json();
}

/** One aggregation bucket of matured outcomes (breakdown value, or the
 *  detector total when key === "totale"). Rates are percentages (0..100). */
export type DetectorPerfCell = {
  key: string;
  n: number;
  abs_hit_rate: number;
  /** Over rows with a market-neutral label only; null when none have one. */
  mkt_neutral_hit_rate: number | null;
  avg_fwd_return: number;
  /** n < min_n → thin evidence, render muted with an "n<30" chip. */
  low_confidence: boolean;

  /** Non-overlapping forward windows the rows span. `n` counts rows, and rows
   *  that share a forward window are not independent draws — a 21-day signal
   *  firing on 20 stocks in one day is ONE observation, not twenty. This is
   *  the number a rate should be trusted in proportion to. Null on replay
   *  cells (the artifact stores counts, not signal dates). */
  effective_n: number | null;
  /** The forward horizon that set the block length. It EXPLAINS effective_n:
   *  over one identical span a 5-day detector yields ~16 independent windows
   *  and a 63-day one yields 1. */
  horizon_days: number | null;
  /** Wilson 95% bounds on `mkt_neutral_hit_rate`, sized by `effective_n`. */
  skill_ci_low: number | null;
  skill_ci_high: number | null;
  /** "above" / "below" only where the interval clears 50 outright, else
   *  "inconclusive". NOT the same vocabulary as the calibration artifact's
   *  edge/coinflip/negative, which keys on a point estimate with no sample
   *  behind it — same word, different bar would be worse than no word. */
  skill_verdict: "above" | "below" | "inconclusive" | null;
};

/** One detector's totals + the three orthogonal breakdowns. */
export type DetectorPerfRow = {
  detector: string;
  total: DetectorPerfCell;
  by_regime: DetectorPerfCell[]; // bull / bear / flat / n-d
  by_tone: DetectorPerfCell[]; // bull / bear
  by_strength: DetectorPerfCell[]; // <60 / 60-74 / >=75 / n-d
};

/** Coverage honesty header: the warehouse is young and partial — the UI must
 *  say so instead of implying complete coverage. */
export type DetectorPerfMeta = {
  total_rows: number;
  n_detectors: number;
  n_detectors_universe: number; // 17
  date_min: string | null;
  date_max: string | null;
  min_n: number;
  computed_at: string;
};

export type DetectorPerformance = {
  meta: DetectorPerfMeta;
  detectors: DetectorPerfRow[]; // sorted by descending total n
};

export async function fetchDetectorPerformance(): Promise<DetectorPerformance> {
  const r = await fetch("/api/platform/detector-performance", {
    credentials: "include",
  });
  if (!r.ok) throw new Error(`detector-performance ${r.status}`);
  return r.json();
}

export async function runProbesNow(): Promise<{ accepted: boolean }> {
  const r = await fetch("/api/platform/probes/run", {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`probes ${r.status}`);
  return r.json();
}

/** {refreshing, progress_pct} of the manual probe run — same contract
 *  as the pre-market card's progress, polled while the spinner shows. */
export async function fetchProbeProgress(): Promise<{
  refreshing: boolean;
  progress_pct: number;
}> {
  const r = await fetch("/api/platform/probes/progress", {
    credentials: "include",
  });
  if (!r.ok) throw new Error(`probe-progress ${r.status}`);
  return r.json();
}

export async function fetchLogs(params: {
  level?: string;
  module?: string;
  search?: string;
  limit?: number;
}): Promise<LogRecord[]> {
  const q = new URLSearchParams();
  if (params.level) q.set("level", params.level);
  if (params.module) q.set("module", params.module);
  if (params.search) q.set("search", params.search);
  if (params.limit) q.set("limit", String(params.limit));
  const r = await fetch(`/api/platform/logs?${q}`, { credentials: "include" });
  if (!r.ok) throw new Error(`logs ${r.status}`);
  return r.json();
}

/** One scrape target. Named, not just counted: "1 target giù" sends you to
 *  kubectl — the job name is the answer. */
export type InfraComponent = {
  job: string;
  namespace: string;
  up: boolean;
};

/** Cluster + observability rollup, read from Prometheus.
 *
 *  Every count is nullable and that is the contract: a query that could not
 *  run reads as UNAVAILABLE, never as zero. "0 target giù" and "non ho potuto
 *  chiedere" are opposite statements, and drawing the second as the first is
 *  how a monitoring panel goes green by going blind. */
export type InfraHealth = {
  available: boolean;
  error: string | null;
  prometheus_url: string | null;
  targets_up: number | null;
  targets_down: number | null;
  down_targets: string[];
  /** Watchdog excluded — it fires forever by design, as the canary proving
   *  Alertmanager delivers. */
  alerts_firing: number | null;
  firing_alerts: string[];
  restarts_24h: number | null;
  memory_pct: number | null;
  cert_days: number | null;
  /** Null when nobody scrapes argocd-metrics: "non monitorato" is honest, a
   *  fabricated sync status is not. */
  argocd: { sync: string; health: string } | null;
  components: InfraComponent[];
};

export async function fetchInfraHealth(): Promise<InfraHealth> {
  const r = await fetch("/api/platform/infra", { credentials: "include" });
  if (!r.ok) throw new Error(`infra ${r.status}`);
  return r.json();
}
