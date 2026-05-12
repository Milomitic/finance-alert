"""Shared helper to turn a ScanRun row into the API-shaped status DTO.

Used by both the alert-scan endpoint (`/api/alerts/scan-status`) and the
score-recompute endpoint (`/api/scores/recompute-status`). The ScanRun
schema is shared via the `kind` discriminator; the status DTO shape is
identical for both kinds — only the consumer (which toast / which set of
labels) differs.

Keeping this in a small module avoids cross-router imports (api.scores
importing a private `_build_scan_status` from api.alerts is the kind of
coupling that bites later when the two routers diverge).
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.models import ScanRun
from app.schemas.alert import ScanStatusOut


# Heartbeat threshold (seconds) past which a 'running' row is considered
# stuck and the UI surfaces a "Stop (forzato)" affordance. Same value for
# both kinds — score-recompute heartbeats fire ~10× per second on a
# warm cache, so 120s is a generous safety margin for both.
SCAN_STALE_THRESHOLD_SEC = 120


def build_scan_status_out(latest: ScanRun) -> ScanStatusOut:
    """Derive stale flag + seconds-since-heartbeat from a ScanRun row.

    Returns the `ScanStatusOut` DTO the API endpoints serialise. The
    `is_stale` flag is True iff the run is 'running' AND the most recent
    progress heartbeat (or started_at as fallback) is older than
    `SCAN_STALE_THRESHOLD_SEC`.
    """
    is_running = latest.status == "running"
    seconds_since_progress: int | None = None
    is_stale = False
    if is_running:
        ref = latest.last_progress_at or latest.started_at
        if ref is not None:
            # SQLite returns naive datetimes — coerce to UTC for the diff.
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=UTC)
            seconds_since_progress = int((datetime.now(UTC) - ref).total_seconds())
            is_stale = seconds_since_progress > SCAN_STALE_THRESHOLD_SEC
    return ScanStatusOut(
        is_running=is_running,
        last_run_id=latest.id,
        trigger=latest.trigger,
        status=latest.status,
        phase=latest.phase,
        started_at=latest.started_at,
        completed_at=latest.completed_at,
        last_progress_at=latest.last_progress_at,
        progress_done=latest.progress_done,
        progress_total=latest.progress_total,
        stocks_scanned=latest.stocks_scanned,
        stocks_skipped=latest.stocks_skipped,
        alerts_fired=latest.alerts_fired,
        current_target=latest.current_target,
        error_message=latest.error_message,
        is_stale=is_stale,
        seconds_since_last_progress=seconds_since_progress,
    )
