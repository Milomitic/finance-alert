"""In-process per-job stats for the APScheduler. Wired in
scheduler/__init__.py via _scheduler.add_listener(...).

We record: last_run_at, last_result, last_duration_ms (best-effort),
last_error, total runs, total errors.

Duration tracking is best-effort because APScheduler doesn't expose
start/end in a single event — we pair EVENT_JOB_SUBMITTED (executor
handoff) with the matching EXECUTED/ERROR event per job_id. The delta
includes any executor queue wait, which is fine for a visual indicator
("the scan took 4m" / "this job suddenly takes 10× longer"); we are not
building a profiler.
"""
import os
from dataclasses import asdict, dataclass, fields
from threading import Lock
from time import time

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
)
from loguru import logger

from app.core import persist_json

# Persist job stats across restarts so the Salute "Scheduler" card keeps each
# job's last run/result/error instead of showing "never run" until it refires.
_STATE_FILE = persist_json.data_path("scheduler_metrics.json")


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
        # job_id → submit timestamp (EVENT_JOB_SUBMITTED). Consumed by the
        # matching EXECUTED/ERROR event to compute last_duration_ms. Not
        # persisted: an in-flight run doesn't survive a restart anyway.
        self._started: dict[str, float] = {}
        self._lock = Lock()

    def on_event(self, event) -> None:
        """APScheduler listener entry point. `event.code` identifies the
        event type; we handle SUBMITTED (start-of-run marker for duration),
        EXECUTED, ERROR, MISSED."""
        try:
            jid = event.job_id
            if event.code == EVENT_JOB_SUBMITTED:
                # Start marker only — no stat row mutation, no disk write.
                with self._lock:
                    self._started[jid] = time()
                return
            with self._lock:
                s = self._stats.setdefault(jid, JobStat(job_id=jid))
                now = time()
                s.last_run_at = now
                if event.code in (EVENT_JOB_EXECUTED, EVENT_JOB_ERROR):
                    # Pair with the SUBMITTED marker; a missing marker (e.g.
                    # restart mid-run, listener attached late) keeps the
                    # previous duration instead of writing garbage.
                    started = self._started.pop(jid, None)
                    if started is not None:
                        s.last_duration_ms = round((now - started) * 1000.0, 1)
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
            self._persist()
        except Exception as exc:  # noqa: BLE001 — listener must not raise
            logger.warning(f"[scheduler_metrics] listener failed: {exc!r}")

    def snapshot(self) -> list[JobStat]:
        with self._lock:
            return list(self._stats.values())

    def snapshot_dict(self) -> list[dict]:
        """Same as snapshot() but as plain dicts (for JSON serialization)."""
        return [asdict(s) for s in self.snapshot()]

    def to_dict(self) -> dict[str, dict]:
        """Serialize stats keyed by job_id (pure; no IO)."""
        with self._lock:
            return {jid: asdict(s) for jid, s in self._stats.items()}

    def from_dict(self, data: dict) -> int:
        """Load stats from a serialized dict (pure; no IO). Returns count loaded."""
        known = {f.name for f in fields(JobStat)}
        with self._lock:
            for jid, d in data.items():
                if not isinstance(d, dict):
                    continue
                clean = {k: v for k, v in d.items() if k in known}
                clean["job_id"] = jid
                self._stats[jid] = JobStat(**clean)
            return len(self._stats)

    def load_from_disk(self) -> int:
        """Rehydrate job stats from disk at boot. No-op under pytest."""
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return 0
        data = persist_json.read_json(_STATE_FILE)
        if not data:
            return 0
        return self.from_dict(data)

    def _persist(self) -> None:
        """Write job stats to disk (called on each scheduler event). No-op under pytest."""
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        persist_json.write_json(_STATE_FILE, self.to_dict())


_INSTANCE = SchedulerMetrics()


def install_listener(scheduler) -> None:
    """Attach the singleton listener to the given BackgroundScheduler.
    Call once at scheduler creation time."""
    scheduler.add_listener(
        _INSTANCE.on_event,
        EVENT_JOB_SUBMITTED | EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
    )
