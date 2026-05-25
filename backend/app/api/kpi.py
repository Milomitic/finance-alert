"""Engine-monitoring KPI endpoint (Fase B).

Serves the "Salute motori" panel: the recent scan + daily-rollup KPI series
captured by `kpi_service`, plus derived health `flags`. Read-only; the heavy
capture happens at scan-end and in the daily cron, so this is a cheap read.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.services import kpi_service

router = APIRouter(prefix="/api/kpi", tags=["kpi"])


@router.get("/monitor")
def get_monitor(
    days: Annotated[int, Query(ge=1, le=365)] = 90,
    scan_limit: Annotated[int, Query(ge=1, le=500)] = 60,
    rollup_limit: Annotated[int, Query(ge=1, le=365)] = 90,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """Recent scan + daily-rollup KPI snapshots (newest first) plus derived
    health flags. Used by the Settings "Salute motori" panel."""
    scans = kpi_service.recent(db, kind="scan", days=days, limit=scan_limit)
    rollups = kpi_service.recent(db, kind="daily_rollup", days=days, limit=rollup_limit)
    flags = kpi_service.compute_flags(scans, rollups)
    return {"scans": scans, "rollups": rollups, "flags": flags}
