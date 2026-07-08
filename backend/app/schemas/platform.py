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
    # "healthy" | "degraded" | "failing" | "unavailable" (plan-gated: all
    # failures HTTP 403 — slate chip, excluded from the banner rollup) |
    # "idle" | "stale" (no success within the source's expected cadence —
    # dead cron/probe with frozen-green counters)
    health: str
    calls_last_minute: int | None
    calls_last_day: int | None
    # Lowercase substrings that identify this source's log lines (module or
    # message). The UI's "click a source → filter live logs" uses these.
    log_match: list[str] = []


class SchedulerJobStatOut(BaseModel):
    """One scheduler job: REGISTERED metadata (next_run_time + trigger, from
    APScheduler's live job list) merged with the event stats. Jobs that have
    never fired still appear (runs=0, last_* None) — a cron that silently
    never runs must be visible, not absent (audit 2026-07-08)."""
    job_id: str
    last_run_at: float | None
    last_result: str | None
    last_duration_ms: float | None
    last_error: str | None
    runs: int
    errors: int
    # Next scheduled fire time (epoch seconds). None when the job is not
    # currently registered (stats-only leftover) or the scheduler is down.
    next_run_time: float | None = None
    # Human-readable trigger repr, e.g. "cron[hour='23', minute='30']".
    trigger: str | None = None


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


class OhlcvFreshnessOut(BaseModel):
    """Freshness of the STORED OHLCV (what scans read): newest bar date +
    how many stocks have a bar on that date. Memoized 60s server-side."""
    max_date: str | None = None      # ISO "YYYY-MM-DD"; None on an empty table
    stocks_at_max: int = 0


class CacheStatsOut(BaseModel):
    fundamentals: CacheKindStatOut
    news: CacheKindStatOut
    db: dict   # {"size_mb": float}
    ohlcv: OhlcvFreshnessOut = OhlcvFreshnessOut()


class GapSuggestionOut(BaseModel):
    """Gap-analysis hint (data_source_metrics.analyse_gaps): an operation
    whose every source is failing/degraded, with a fallback suggestion.
    Folded into the platform payload when the dedicated
    /api/health/data-sources endpoint was deleted (audit 2026-07-08)."""
    op: str
    why: str
    suggestion: str


class PlatformHealthOut(BaseModel):
    data_sources: list[DataSourceMetricOut]
    yfinance_breaker: dict   # the existing yfinance_health.status() shape
    scheduler: list[SchedulerJobStatOut]
    scans: list[RecentScanOut]
    cache: CacheStatsOut
    # Server-side rollup (health_rollup.compute_rollup): one truth for the
    # banner/SSE/Telegram instead of N client-side derivations. The frontend
    # keeps its old derivation only as a fallback for pre-rollup payloads.
    overall: str = "operational"     # "operational" | "degraded" | "outage"
    reasons: list[str] = []          # Italian, human-readable, outage first
    # Gap-analysis hints — empty when every op has at least one healthy source.
    suggestions: list[GapSuggestionOut] = []


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
    # True when the historical-replay artifact (B4-5) is present and the
    # response carries the separate `replay` segment.
    replay_available: bool = False


class DetectorReplayRowOut(BaseModel):
    """One detector's REPLAY aggregates — same cube shape as the live row,
    but sourced from the historical-replay artifact (source='replay'), not
    from matured alerts. Rendered as a separate segment, never merged."""
    detector: str
    total: DetectorPerfCellOut
    by_regime: list[DetectorPerfCellOut]
    by_tone: list[DetectorPerfCellOut]
    by_strength: list[DetectorPerfCellOut]


class DetectorReplayOut(BaseModel):
    """Historical-replay segment (app.scripts.backfill_replay_outcomes).
    A DIFFERENT population from the live warehouse — the replay has no
    emission-gate survivorship of the live settings history — so the UI must
    label it 'replay' and never blend it into live hit rates."""
    generated_at: str | None = None   # artifact generation timestamp (ISO)
    n_signals: int                    # replayed occurrences aggregated
    date_min: str | None = None       # earliest observation bar covered (ISO)
    date_max: str | None = None       # latest observation bar covered (ISO)
    params: dict | None = None        # replay run parameters (years/step/window/...)
    detectors: list[DetectorReplayRowOut]   # sorted by descending total n


class DetectorPerformanceOut(BaseModel):
    meta: DetectorPerfMetaOut
    detectors: list[DetectorPerfRowOut]   # sorted by descending total n
    # Present only when the replay artifact exists (meta.replay_available).
    replay: DetectorReplayOut | None = None
