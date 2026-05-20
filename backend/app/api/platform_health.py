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

from app.api.deps import get_current_user, get_db
from app.core.log_buffer import _INSTANCE as log_buffer
from app.models import Alert, ScanRun, User
from app.schemas.platform import (
    LogRecordOut,
    PlatformHealthOut,
    RecentScanOut,
    SchedulerJobStatOut,
)
from app.services import cache_metrics, source_catalog, yfinance_health
from app.services.scheduler_metrics import _INSTANCE as scheduler_metrics

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


def _sources_payload() -> list[dict]:
    """Catalog-enriched data-source snapshot. Includes every known source
    (idle entries with zero counts) plus rate-limit usage when applicable."""
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
        }
        for s in source_catalog.full_snapshot()
    ]


@router.get("/health", response_model=PlatformHealthOut)
def health_snapshot(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PlatformHealthOut:
    return PlatformHealthOut(
        data_sources=_sources_payload(),
        yfinance_breaker=yfinance_health.status(),
        scheduler=[SchedulerJobStatOut(**s) for s in scheduler_metrics.snapshot_dict()],
        scans=_recent_scans(db),
        cache=cache_metrics.snapshot(),
    )


@router.post("/probes/run", status_code=202)
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
        snap_dict = {
            "data_sources": _sources_payload(),
            "yfinance_breaker": yfinance_health.status(),
            "scheduler": scheduler_metrics.snapshot_dict(),
            "scans": [s.model_dump() for s in _recent_scans(db)],
            "cache": cache_metrics.snapshot(),
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
