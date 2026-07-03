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
  health: "healthy" | "degraded" | "failing" | "idle" | string;
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

export type PlatformHealth = {
  data_sources: DataSourceMetric[];
  yfinance_breaker: Record<string, unknown>;
  scheduler: SchedulerJobStat[];
  scans: RecentScan[];
  cache: {
    fundamentals: CacheKindStat;
    news: CacheKindStat;
    db: { size_mb: number };
  };
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
