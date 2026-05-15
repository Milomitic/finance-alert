"""Read-only API for the platform-health UI. Two REST endpoints:
- GET /health    -> combined snapshot
- GET /logs      -> filtered log slice
(SSE /stream endpoint will be added in Task 7)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
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
from app.services import cache_metrics, data_source_metrics, yfinance_health
from app.services.scheduler_metrics import _INSTANCE as scheduler_metrics

router = APIRouter(prefix="/api/platform", tags=["platform"])


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
            started_at=r.started_at.isoformat() if r.started_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            duration_s=duration_s,
            progress_done=r.progress_done,
            progress_total=r.progress_total,
            alerts_count=alerts_count,
            error_message=r.error_message,
        ))
    return out


@router.get("/health", response_model=PlatformHealthOut)
def health_snapshot(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PlatformHealthOut:
    metrics = data_source_metrics.snapshot()
    return PlatformHealthOut(
        data_sources=[
            {
                "source": m.source,
                "op": m.op,
                "success": m.success,
                "failure": m.failure,
                "success_rate": m.success_rate,
                "last_success_at": m.last_success_at,
                "last_failure_at": m.last_failure_at,
                "last_failure_reason": m.last_failure_reason,
                "health": m.health,
            }
            for m in metrics
        ],
        yfinance_breaker=yfinance_health.status(),
        scheduler=[SchedulerJobStatOut(**s) for s in scheduler_metrics.snapshot_dict()],
        scans=_recent_scans(db),
        cache=cache_metrics.snapshot(),
    )


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
