"""Scan run audit log: tracks each invocation of the alert scan job for live UI feedback."""
import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index as SAIndex, Integer, String, Text, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


# `kind` discriminator values. The schema is shared between alert-scan and
# score-recompute jobs since both fit the same progress-tracking shape
# (status / phase / heartbeat / progress / counters / error_message).
# Filtering on read keeps each job's UI surface independent.
KIND_ALERTS_SCAN = "alerts_scan"
KIND_SCORE_RECOMPUTE = "score_recompute"


class ScanRun(Base):
    """One row per tracked background job (alert scan OR score recompute).

    The `kind` column discriminates: 'alerts_scan' rows feed
    /api/alerts/scan-status, 'score_recompute' rows feed
    /api/scores/recompute-status. Status transitions are the same:
        running -> success | failed
    """

    __tablename__ = "scan_runs"
    __table_args__ = (SAIndex("ix_scan_runs_started_at", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 'alerts_scan' | 'score_recompute'. Defaults at the DB level so legacy
    # rows backfill cleanly via the migration. See KIND_* constants above.
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default=KIND_ALERTS_SCAN, server_default=KIND_ALERTS_SCAN
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # "cron" | "manual"
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "running" | "success" | "failed"
    # Sub-phase while running. Alert-scan emits values like "fetching:planning",
    # "fetching:backfill", "fetching:incremental", "evaluating:loading_rules",
    # "evaluating:scoring"; score-recompute emits "sector_stats" / "scoring".
    # NULL when finished. Widened to 32 chars when sub-phases were introduced
    # — older values ("fetching", "evaluating") still parse fine.
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Heartbeat: bumped every time the worker reports progress. The UI uses
    # `now() - last_progress_at` to detect stuck/orphan scans (worker process
    # crashed but the row still says 'running'). NULL until the first progress
    # callback fires — pre-progress, fall back to started_at for staleness.
    last_progress_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stocks_scanned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stocks_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alerts_fired: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Free-form "what we're touching RIGHT NOW" — typically a ticker, optionally
    # decorated (e.g. "AAPL · chunk 3/12"). Updated alongside the heartbeat so
    # the UI can show a live target instead of just a percentage. NULL when the
    # phase doesn't have a meaningful per-item focus.
    current_target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded list of {phase, started_at, ended_at} entries — one per
    # phase transition. Populated by the SQLAlchemy `set` event listener
    # below: on every `run.phase = X` assignment, the previous phase (if
    # any) gets its `ended_at` stamped, and the new phase appended with
    # `started_at = now`. Powers the per-phase timing breakdown in the
    # ScanLogPanel (Settings → Log scan). Default '[]' for legacy rows
    # so they render as "no phase data" instead of erroring.
    phase_history: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )


@event.listens_for(ScanRun.phase, "set", propagate=True)
def _record_phase_transition(target: ScanRun, value: str | None, _oldvalue: object, _initiator: object) -> None:
    """Maintain `phase_history` automatically on every `run.phase = X`.

    Logic (deliberately NOT relying on `oldvalue` — SQLAlchemy doesn't
    track previous values without `active_history=True`, which would
    cost an extra SELECT per set; instead we infer the previous phase
    from the in-memory phase_history's last open entry):

      - If the last history entry is for the same phase AND still open
        (ended_at is None), no-op — same-value sets shouldn't bloat
        the log (e.g. the chunk loop reassigns the same phase often).
      - Otherwise, close the last open entry (if any) by stamping
        ended_at = now.
      - If the new value is non-None, append a fresh open entry. When
        the run finalizes (`run.phase = None`) we just close the open
        entry without appending a "phase=None" record.

    JSON parse failures degrade silently to an empty list — never
    block a phase set with a deserialization error.
    """
    try:
        history = json.loads(target.phase_history) if target.phase_history else []
        if not isinstance(history, list):
            history = []
    except (TypeError, ValueError):
        history = []

    now_iso = datetime.now(UTC).isoformat()
    last = history[-1] if history else None

    # Same-value, still-open entry → no-op. Avoids cluttering the log
    # when chunk-level code reassigns the same phase per iteration.
    if last and last.get("phase") == value and last.get("ended_at") is None:
        return

    # Close prior open entry, if any.
    if last and last.get("ended_at") is None:
        last["ended_at"] = now_iso

    # Open a new entry — only when the new value is non-None.
    if value is not None:
        history.append({"phase": value, "started_at": now_iso, "ended_at": None})

    target.phase_history = json.dumps(history)
