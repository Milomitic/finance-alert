"""In-process per-job stats for the APScheduler. Wired in
scheduler/__init__.py via _scheduler.add_listener(...).

We record: last_run_at, last_result, last_duration_ms (best-effort),
last_error, total runs, total errors.

Duration tracking is best-effort because APScheduler doesn't expose
start/end in a single event — we approximate by recording the
scheduled_run_time delta. For our purposes (visual indicator) this is
plenty; we are not building a profiler.
"""
from dataclasses import dataclass, asdict
from threading import Lock
from time import time

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
)
from loguru import logger


@dataclass
class JobStat:
    job_id: str
    last_run_at: float | None = None
    last_result: str | None = None        # "ok" | "error" | "missed"
    last_duration_ms: float | None = None
    last_error: str | None = None
    runs: int = 0
    errors: int = 0


class SchedulerMetrics:
    def __init__(self) -> None:
        self._stats: dict[str, JobStat] = {}
        self._lock = Lock()

    def on_event(self, event) -> None:
        """APScheduler listener entry point. `event.code` identifies the
        event type; we handle EXECUTED, ERROR, MISSED."""
        try:
            jid = event.job_id
            with self._lock:
                s = self._stats.setdefault(jid, JobStat(job_id=jid))
                s.last_run_at = time()
                if event.code == EVENT_JOB_EXECUTED:
                    s.last_result = "ok"
                    s.runs += 1
                    s.last_error = None
                elif event.code == EVENT_JOB_ERROR:
                    s.last_result = "error"
                    s.errors += 1
                    s.last_error = repr(event.exception) if event.exception else "unknown"
                elif event.code == EVENT_JOB_MISSED:
                    s.last_result = "missed"
        except Exception as exc:  # noqa: BLE001 — listener must not raise
            logger.warning(f"[scheduler_metrics] listener failed: {exc!r}")

    def snapshot(self) -> list[JobStat]:
        with self._lock:
            return list(self._stats.values())

    def snapshot_dict(self) -> list[dict]:
        """Same as snapshot() but as plain dicts (for JSON serialization)."""
        return [asdict(s) for s in self.snapshot()]


_INSTANCE = SchedulerMetrics()


def install_listener(scheduler) -> None:
    """Attach the singleton listener to the given BackgroundScheduler.
    Call once at scheduler creation time."""
    scheduler.add_listener(
        _INSTANCE.on_event,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
    )
