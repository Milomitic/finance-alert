"""Scan log endpoint — recent scan_runs with per-phase timing breakdown.

Powers the ScanLogPanel in the Settings page (added 2026-05-14). Returns
a flat list of recent scans with the timing of each phase parsed from
`scan_runs.phase_history` (populated by the SQLAlchemy event listener
on `ScanRun.phase` set — see `models/scan_run.py`).

The endpoint does NO scan triggering — read-only summary surface.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import ScanRun, User

router = APIRouter(prefix="/api/scan-runs", tags=["scan-log"])


class PhaseTimingOut(BaseModel):
    """One phase's timing within a scan run. `duration_sec` is null when
    the phase hasn't ended yet (the run is in progress)."""
    phase: str
    started_at: str
    ended_at: str | None
    duration_sec: float | None


class ScanRunSummaryOut(BaseModel):
    id: int
    kind: str
    trigger: str
    status: str  # "running" | "success" | "failed"
    started_at: str
    completed_at: str | None
    total_duration_sec: float | None
    progress_done: int
    progress_total: int
    stocks_scanned: int | None
    stocks_skipped: int | None
    alerts_fired: int | None
    error_message: str | None
    # Per-phase breakdown — empty list for legacy rows that predate the
    # phase_history column. The UI shows "—" in that case.
    phases: list[PhaseTimingOut]


class ScanLogOut(BaseModel):
    runs: list[ScanRunSummaryOut]


def _parse_phase_history(raw: str | None) -> list[PhaseTimingOut]:
    """Decode the JSON-encoded phase_history into typed entries with
    duration_sec computed for closed phases. Bad JSON / missing fields
    degrade silently to an empty list — never blocks the endpoint."""
    if not raw:
        return []
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            return []
    except (TypeError, ValueError):
        return []
    out: list[PhaseTimingOut] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        phase = e.get("phase")
        started = e.get("started_at")
        ended = e.get("ended_at")
        if not isinstance(phase, str) or not isinstance(started, str):
            continue
        duration: float | None = None
        if isinstance(ended, str):
            try:
                duration = (
                    datetime.fromisoformat(ended) - datetime.fromisoformat(started)
                ).total_seconds()
            except ValueError:
                duration = None
        out.append(
            PhaseTimingOut(
                phase=phase,
                started_at=started,
                ended_at=ended if isinstance(ended, str) else None,
                duration_sec=duration,
            )
        )
    return out


@router.get("/recent", response_model=ScanLogOut)
def list_recent_scans(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    kind: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ScanLogOut:
    """Most recent `limit` scan runs, newest first.

    `kind` optionally filters by 'alerts_scan' / 'score_recompute'. None
    returns both interleaved by start time.
    """
    stmt = select(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit)
    if kind is not None:
        stmt = stmt.where(ScanRun.kind == kind)
    rows = db.execute(stmt).scalars().all()

    out: list[ScanRunSummaryOut] = []
    for r in rows:
        # Derive total duration from completed_at when available, else
        # NULL so the UI shows "in corso" / "—" appropriately.
        total: float | None = None
        if r.completed_at and r.started_at:
            try:
                total = (r.completed_at - r.started_at).total_seconds()
            except (TypeError, ValueError):
                total = None
        out.append(
            ScanRunSummaryOut(
                id=r.id,
                kind=r.kind,
                trigger=r.trigger,
                status=r.status,
                started_at=r.started_at.isoformat() if r.started_at else "",
                completed_at=r.completed_at.isoformat() if r.completed_at else None,
                total_duration_sec=total,
                progress_done=r.progress_done or 0,
                progress_total=r.progress_total or 0,
                stocks_scanned=r.stocks_scanned,
                stocks_skipped=r.stocks_skipped,
                alerts_fired=r.alerts_fired,
                error_message=r.error_message,
                phases=_parse_phase_history(r.phase_history),
            )
        )
    return ScanLogOut(runs=out)
