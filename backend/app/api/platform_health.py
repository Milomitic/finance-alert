"""Read-only API for the platform-health UI. Three endpoints:
- GET /health    -> combined snapshot
- GET /logs      -> filtered log slice
- GET /stream    -> SSE stream (snapshot + log push + keepalive)
"""
import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.log_buffer import _INSTANCE as log_buffer
from app.models import Alert, ScanRun, User
from app.schemas.platform import (
    DetectorPerformanceOut,
    LogRecordOut,
    PlatformHealthOut,
    RecentScanOut,
    SchedulerJobStatOut,
    SignalDriftOut,
)
from app.services import (
    cache_metrics,
    data_source_metrics,
    detector_performance_service,
    health_rollup,
    signal_drift_service,
    source_catalog,
    yfinance_health,
)

router = APIRouter(prefix="/api/platform", tags=["platform"])


def _iso_utc(dt: datetime | None) -> str | None:
    """Serialize a datetime as an ISO-8601 string with explicit UTC offset.

    SQLite + SQLAlchemy round-trips ``DateTime(timezone=True)`` columns as
    NAIVE Python datetimes (the timezone is silently dropped). Project
    convention: all timestamps are stored in UTC. We re-attach the
    timezone before serialization so the browser sees ``+00:00`` and
    parses correctly — without this marker, ``new Date(iso)`` in JS
    interprets the string as LOCAL time and a CEST viewer sees scans
    apparently started 2h ago, tripping stuck-scan heuristics."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _recent_scans(db: Session, limit: int = 10) -> list[RecentScanOut]:
    rows = db.execute(
        select(ScanRun).order_by(desc(ScanRun.id)).limit(limit)
    ).scalars().all()
    out: list[RecentScanOut] = []
    for r in rows:
        alerts_count: int | None = None
        if r.started_at and r.completed_at:
            alerts_count = db.execute(
                select(func.count()).select_from(Alert).where(
                    Alert.triggered_at >= r.started_at,
                    Alert.triggered_at <= r.completed_at,
                )
            ).scalar_one()
        duration_s: float | None = None
        if r.started_at and r.completed_at:
            duration_s = (r.completed_at - r.started_at).total_seconds()
        out.append(RecentScanOut(
            id=r.id,
            status=r.status,
            phase=r.phase,
            trigger=r.trigger,
            started_at=_iso_utc(r.started_at),
            completed_at=_iso_utc(r.completed_at),
            duration_s=duration_s,
            progress_done=r.progress_done,
            progress_total=r.progress_total,
            alerts_count=alerts_count,
            error_message=r.error_message,
        ))
    return out


def _sources_payload(sources: list | None = None) -> list[dict]:
    """Catalog-enriched data-source snapshot. Includes every known source
    (idle entries with zero counts) plus rate-limit usage when applicable.
    Accepts a pre-built `full_snapshot()` so callers that also feed the
    rollup don't snapshot twice."""
    if sources is None:
        sources = source_catalog.full_snapshot()
    return [
        {
            "source": s.source, "op": s.op, "label": s.label, "role": s.role,
            "per_minute_limit": s.per_minute_limit,
            "per_day_limit": s.per_day_limit,
            "notes": s.notes,
            "success": s.success, "failure": s.failure,
            "success_rate": s.success_rate,
            "last_success_at": s.last_success_at,
            "last_failure_at": s.last_failure_at,
            "last_failure_reason": s.last_failure_reason,
            "health": s.health,
            "calls_last_minute": s.calls_last_minute,
            "calls_last_day": s.calls_last_day,
            "log_match": s.log_match,
        }
        for s in sources
    ]


def _gap_suggestions() -> list[dict]:
    """Gap-analysis hints (an op whose EVERY source is failing/degraded →
    fallback suggestion). Previously served by the dedicated
    /api/health/data-sources endpoint, which duplicated this snapshot —
    the endpoint was deleted and its one useful half folded in here."""
    return [
        {"op": g.op, "why": g.why, "suggestion": g.suggestion}
        for g in data_source_metrics.analyse_gaps()
    ]


@router.get("/health", response_model=PlatformHealthOut)
def health_snapshot(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PlatformHealthOut:
    sources = source_catalog.full_snapshot()
    breaker = yfinance_health.status()
    # Merged view: every REGISTERED job (next_run_time + trigger) joined with
    # its event stats — jobs are visible BEFORE their first run/error.
    scheduler_jobs = health_rollup.scheduler_jobs_payload()
    scans = _recent_scans(db)
    overall, reasons = health_rollup.compute_rollup(
        sources=sources, breaker=breaker, scheduler=scheduler_jobs, scans=scans
    )
    # Transition push (best-effort, self-gated on state change + cooldown).
    health_rollup.maybe_notify_transition(overall, reasons)
    return PlatformHealthOut(
        data_sources=_sources_payload(sources),
        yfinance_breaker=breaker,
        scheduler=[SchedulerJobStatOut(**s) for s in scheduler_jobs],
        scans=scans,
        cache=cache_metrics.snapshot(),
        overall=overall,
        reasons=reasons,
        suggestions=_gap_suggestions(),
    )


@router.get("/signal-drift", response_model=SignalDriftOut)
def signal_drift(
    window_days: Annotated[int, Query(ge=7, le=365)] = 90,
    min_n: Annotated[int, Query(ge=1, le=500)] = 30,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SignalDriftOut:
    """Per-detector signal DRIFT / DECAY monitor (read-only, computed on demand).

    Compares each detector's REALISED recent hit-rate (over MATURED signal
    alerts, read from the `signal_outcomes` warehouse — `abs_hit` is labeled
    with the same definition the calibration was built on) against its
    CALIBRATED base rate, and flags drift when the base rate falls outside the
    recent rate's Wilson 95% confidence interval (and the matured sample clears
    `min_n`). Tells us WHEN to retune a detector on evidence, instead of
    continuously. Sorted by descending |delta|. Outcomes mature at scan end, so
    the window reflects the warehouse "as of the last scan".

      window_days  rolling window of matured alerts to measure (calendar days)
      min_n        minimum matured sample before a detector can be flagged
    """
    rows = signal_drift_service.compute_signal_drift(
        db, window_days=window_days, min_n=min_n
    )
    summary = signal_drift_service.drift_summary(
        rows, window_days=window_days, min_n=min_n
    )
    return SignalDriftOut(summary=summary, detectors=rows)


@router.get("/detector-performance", response_model=DetectorPerformanceOut)
def detector_performance(
    min_n: Annotated[int, Query(ge=1, le=500)] = 30,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DetectorPerformanceOut:
    """Detector performance explorer (read-only, computed on demand).

    Aggregates the `signal_outcomes` warehouse into a per-detector cube:
    overall totals plus breakdowns by regime-at-signal (bull/bear/n-d), tone
    (bull/bear) and Forza band (<60 / 60-74 / >=75 / n-d). Per cell: n,
    absolute hit-rate, market-neutral hit-rate and mean forward return, with a
    `low_confidence` honesty flag when n < min_n (default 30 — the same floor
    the drift monitor uses). The `meta` envelope states the warehouse's actual
    coverage (rows, detectors present vs the 17-detector universe, date range)
    because long-horizon outcomes mature months after their signals — the UI
    must surface the partial coverage rather than imply completeness.

      min_n   per-cell sample floor below which a cell is flagged low_confidence
    """
    data = detector_performance_service.compute_detector_performance(
        db, min_n=min_n
    )
    return DetectorPerformanceOut(**data)


@router.post("/probes/run", status_code=202, dependencies=[Depends(require_json)])
def run_probes_now(
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
) -> dict:
    """Manually trigger all health probes (fast + slow). Runs in the
    BACKGROUND (returns 202 immediately) so the UI "Aggiorna" button
    can show live progress instead of a blind ~5-10s block — poll
    GET /probes/progress for {refreshing, progress_pct} (same contract
    as the pre-market card). Each probe records to
    `data_source_metrics` so the next /health snapshot reflects it.
    De-duped: a run already in flight keeps going, this is a no-op.

    Marketaux note: consumes 1 of its 100/day quota (slow set includes
    its probe), so don't hammer this."""
    from app.services import probes

    if not probes.progress()["refreshing"]:
        background.add_task(probes.run_all_probes)
    return {"accepted": True}


@router.get("/probes/progress")
def probes_progress(
    _user: User = Depends(get_current_user),
) -> dict:
    """{refreshing, progress_pct} of the manual probe run — polled by
    the Salute "Aggiorna" spinner. Same shape the pre-market card uses
    so the frontend reuses one progress component."""
    from app.services import probes

    return probes.progress()


@router.get("/logs", response_model=list[LogRecordOut])
def logs(
    level: Annotated[str | None, Query()] = None,
    module: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    _user: User = Depends(get_current_user),
) -> list[LogRecordOut]:
    records = log_buffer.get_snapshot(
        level=level, module=module, search=search, limit=limit
    )
    return [LogRecordOut(**r) for r in records]


@router.get("/stream")
async def stream(
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE stream emitting:
       - event: snapshot   (initial + every 5s)
       - event: log        (on each new log record)
       - : keepalive       (every 30s, SSE comment)
    """
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=1000)
    loop = asyncio.get_running_loop()

    def on_log(record: dict) -> None:
        # Called from the loguru sink thread. Schedule the put on the
        # event loop so we cross thread boundaries safely.
        try:
            payload = json.dumps(record, default=str)

            def _enqueue() -> None:
                try:
                    queue.put_nowait(("log", payload))
                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(_enqueue)
        except Exception:  # noqa: BLE001 — never break logging
            pass

    unsub = log_buffer.subscribe(on_log)

    async def _snapshot_payload() -> str:
        sources = source_catalog.full_snapshot()
        breaker = yfinance_health.status()
        scheduler_jobs = health_rollup.scheduler_jobs_payload()
        scans = _recent_scans(db)
        overall, reasons = health_rollup.compute_rollup(
            sources=sources, breaker=breaker,
            scheduler=scheduler_jobs, scans=scans,
        )
        # Same transition push as the REST snapshot — self-gated on state
        # change + 6h cooldown, so the 5s SSE cadence can't spam Telegram.
        # Off-loop thread: the (rare) Telegram POST must not block the SSE
        # event loop for its 10s timeout.
        await asyncio.to_thread(health_rollup.maybe_notify_transition, overall, reasons)
        snap_dict = {
            "data_sources": _sources_payload(sources),
            "yfinance_breaker": breaker,
            "scheduler": scheduler_jobs,
            "scans": [s.model_dump() for s in scans],
            "cache": cache_metrics.snapshot(),
            "overall": overall,
            "reasons": reasons,
            "suggestions": _gap_suggestions(),
        }
        return json.dumps(snap_dict, default=str)

    async def _snapshot_loop() -> None:
        while True:
            await asyncio.sleep(5.0)
            try:
                payload = await _snapshot_payload()
                queue.put_nowait(("snapshot", payload))
            except asyncio.QueueFull:
                pass
            except Exception:  # noqa: BLE001
                pass

    async def event_gen():
        snapshot_task = None
        try:
            initial = await _snapshot_payload()
            yield f"event: snapshot\ndata: {initial}\n\n"
            snapshot_task = asyncio.create_task(_snapshot_loop())
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event_type, data = await asyncio.wait_for(
                        queue.get(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event_type}\ndata: {data}\n\n"
        finally:
            if snapshot_task is not None:
                snapshot_task.cancel()
            unsub()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
