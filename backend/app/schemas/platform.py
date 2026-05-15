"""Pydantic response schemas for /api/platform/* endpoints."""
from pydantic import BaseModel


class DataSourceMetricOut(BaseModel):
    source: str
    op: str
    success: int
    failure: int
    success_rate: float
    last_success_at: float | None
    last_failure_at: float | None
    last_failure_reason: str | None
    health: str


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
    oldest_age_s: float | None


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
