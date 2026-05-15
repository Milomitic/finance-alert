/**
 * Typed REST + SSE client for /api/platform/*.
 * Mirrors the Pydantic shapes in backend/app/schemas/platform.py.
 */
export type DataSourceMetric = {
  source: string;
  op: string;
  success: number;
  failure: number;
  success_rate: number;
  last_success_at: number | null;
  last_failure_at: number | null;
  last_failure_reason: string | null;
  health: string;
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
  oldest_age_s: number | null;
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
