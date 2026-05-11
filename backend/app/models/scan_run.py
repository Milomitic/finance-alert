"""Scan run audit log: tracks each invocation of the alert scan job for live UI feedback."""
from datetime import datetime

from sqlalchemy import DateTime, Index as SAIndex, Integer, String, Text, func
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
    # Sub-phase while running: alert-scan emits "fetching" / "evaluating";
    # score-recompute emits "sector_stats" / "scoring". NULL when finished.
    phase: Mapped[str | None] = mapped_column(String(16), nullable=True)
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
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
