"""Pydantic response schemas for /api/platform/* endpoints."""
from pydantic import BaseModel


class DataSourceMetricOut(BaseModel):
    """Catalog entry + live counters + rate-limit usage for one (source, op).

    Mirrors `app.services.source_catalog.SourceWithUsage`. The frontend
    uses `role` to group sources (primary / fallback / scheduled), the
    rate-limit fields to render usage progress bars, and `health` to
    color-code the status badge."""
    source: str
    op: str
    label: str
    role: str                          # "primary" | "fallback" | "scheduled"
    per_minute_limit: int | None
    per_day_limit: int | None
    notes: str
    success: int
    failure: int
    success_rate: float
    last_success_at: float | None
    last_failure_at: float | None
    last_failure_reason: str | None
    health: str                        # "healthy" | "degraded" | "failing" | "idle"
    calls_last_minute: int | None
    calls_last_day: int | None
    # Lowercase substrings that identify this source's log lines (module or
    # message). The UI's "click a source → filter live logs" uses these.
    log_match: list[str] = []


class SchedulerJobStatOut(BaseModel):
    job_id: str
    last_run_at: float | None
    last_result: str | None
    last_duration_ms: float | None
    last_error: str | None
    runs: int
    errors: int


class RecentScanOut(BaseModel):
    id: int
    status: str
    phase: str | None
    trigger: str
    started_at: str | None
    completed_at: str | None
    duration_s: float | None
    progress_done: int | None
    progress_total: int | None
    alerts_count: int | None
    error_message: str | None


class CacheKindStatOut(BaseModel):
    l1_entries: int
    l2_entries: int
    # L1 (in-process) freshness: oldest = staleness tail, newest = freshness head.
    oldest_age_s: float | None
    newest_age_s: float | None = None
    # L2 (persisted fetch_cache) freshness — survives restarts.
    l2_oldest_age_s: float | None = None
    l2_newest_age_s: float | None = None


class CacheStatsOut(BaseModel):
    fundamentals: CacheKindStatOut
    news: CacheKindStatOut
    db: dict   # {"size_mb": float}


class PlatformHealthOut(BaseModel):
    data_sources: list[DataSourceMetricOut]
    yfinance_breaker: dict   # the existing yfinance_health.status() shape
    scheduler: list[SchedulerJobStatOut]
    scans: list[RecentScanOut]
    cache: CacheStatsOut


class LogRecordOut(BaseModel):
    ts: float
    level: str
    module: str
    function: str
    line: int
    message: str
    exception: str | None = None


class SignalDriftRowOut(BaseModel):
    """One detector's drift verdict: realised recent hit-rate vs the calibrated
    base rate, with the Wilson band that decides significance. All rates are
    percentages (0..100)."""
    detector: str
    n_matured: int                 # matured signal alerts in the recent window
    recent_hit_rate: float         # realised hit-rate over those matured alerts
    base_rate: float               # calibrated base rate (signal_calibration.json)
    delta: float                   # recent_hit_rate - base_rate (signed)
    ci_low: float                  # Wilson lower bound on recent_hit_rate
    ci_high: float                 # Wilson upper bound on recent_hit_rate
    drift_flag: bool               # base_rate outside [ci_low, ci_high] AND n>=min_n
    direction: str                 # "decaying" | "improving" | "stable"
    horizon_days: int              # detector's forward horizon (trading days)


class SignalDriftSummaryOut(BaseModel):
    n_detectors: int               # detectors with >=1 matured alert in window
    n_flagged: int
    n_decaying: int
    n_improving: int
    window_days: int               # rolling window of matured alerts (calendar)
    min_n: int                     # min matured-sample size before a flag
    computed_at: str               # ISO-8601 UTC


class SignalDriftOut(BaseModel):
    summary: SignalDriftSummaryOut
    detectors: list[SignalDriftRowOut]   # sorted by descending |delta|


class DetectorPerfCellOut(BaseModel):
    """One aggregation bucket of matured outcomes (a breakdown value, or the
    detector total when key == "totale"). All rates are percentages (0..100)."""
    key: str                             # bucket label: "bull"/"bear"/"<60"/"n/d"/...
    n: int                               # matured outcome rows in the bucket
    abs_hit_rate: float                  # absolute directional hit-rate
    mkt_neutral_hit_rate: float | None   # over rows with a market-neutral label; None if none
    avg_fwd_return: float                # mean forward return over the horizon (%)
    low_confidence: bool                 # n < min_n → thin evidence, render muted


class DetectorPerfRowOut(BaseModel):
    """One detector's totals + the three orthogonal breakdowns."""
    detector: str
    total: DetectorPerfCellOut
    by_regime: list[DetectorPerfCellOut]     # bull / bear / flat / n-d (null regime)
    by_tone: list[DetectorPerfCellOut]       # bull / bear
    by_strength: list[DetectorPerfCellOut]   # <60 / 60-74 / >=75 / n-d (null strength)


class DetectorPerfMetaOut(BaseModel):
    """Coverage honesty header: the warehouse is young, entire detectors are
    still absent (63d horizons mature months after their signals) — the UI
    must SAY so instead of implying complete coverage."""
    total_rows: int                # matured outcome rows aggregated
    n_detectors: int               # detectors with >=1 matured outcome
    n_detectors_universe: int      # the full detector universe (17)
    date_min: str | None           # earliest signal_date covered (ISO)
    date_max: str | None           # latest signal_date covered (ISO)
    min_n: int                     # per-cell low_confidence threshold
    computed_at: str               # ISO-8601 UTC


class DetectorPerformanceOut(BaseModel):
    meta: DetectorPerfMetaOut
    detectors: list[DetectorPerfRowOut]   # sorted by descending total n
