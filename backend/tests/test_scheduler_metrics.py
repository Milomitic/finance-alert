"""Stats per job: last_run, last_result, last_duration_ms, runs, errors.
The listener consumes APScheduler events; we synthesize them here."""
import time
from types import SimpleNamespace

from app.services.scheduler_metrics import SchedulerMetrics


def _executed_event(job_id: str, retval=None) -> SimpleNamespace:
    """Synthesize an apscheduler JobExecutionEvent."""
    return SimpleNamespace(
        code=4096,                       # EVENT_JOB_EXECUTED
        job_id=job_id,
        scheduled_run_time=None,
        retval=retval,
        exception=None,
        traceback=None,
    )


def _error_event(job_id: str, exception=None) -> SimpleNamespace:
    return SimpleNamespace(
        code=8192,                       # EVENT_JOB_ERROR
        job_id=job_id,
        scheduled_run_time=None,
        retval=None,
        exception=exception or RuntimeError("boom"),
        traceback="Traceback...",
    )


def _missed_event(job_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        code=16384,                      # EVENT_JOB_MISSED
        job_id=job_id,
        scheduled_run_time=None,
        retval=None,
        exception=None,
        traceback=None,
    )


def test_empty_snapshot():
    m = SchedulerMetrics()
    assert m.snapshot() == []


def test_executed_event_records_stats():
    m = SchedulerMetrics()
    m.on_event(_executed_event("scan_alerts"))
    snap = m.snapshot()
    assert len(snap) == 1
    s = snap[0]
    assert s.job_id == "scan_alerts"
    assert s.last_result == "ok"
    assert s.runs == 1
    assert s.errors == 0
    assert s.last_run_at is not None
    assert s.last_error is None


def test_error_event_increments_errors_and_keeps_last_error():
    m = SchedulerMetrics()
    m.on_event(_error_event("refresh_fred", exception=ValueError("upstream down")))
    snap = m.snapshot()
    s = snap[0]
    assert s.last_result == "error"
    assert s.errors == 1
    assert "upstream down" in (s.last_error or "")


def test_missed_event_recorded_as_missed():
    m = SchedulerMetrics()
    m.on_event(_missed_event("scan_alerts"))
    snap = m.snapshot()
    assert snap[0].last_result == "missed"


def test_subsequent_events_overwrite_last_fields_but_accumulate_counters():
    m = SchedulerMetrics()
    m.on_event(_executed_event("scan_alerts"))
    time.sleep(0.001)
    m.on_event(_error_event("scan_alerts"))
    snap = m.snapshot()
    s = snap[0]
    assert s.runs == 1
    assert s.errors == 1
    assert s.last_result == "error"


def test_multiple_jobs_tracked_independently():
    m = SchedulerMetrics()
    m.on_event(_executed_event("a"))
    m.on_event(_executed_event("b"))
    m.on_event(_error_event("a"))
    snap = m.snapshot()
    by_id = {s.job_id: s for s in snap}
    assert by_id["a"].errors == 1
    assert by_id["b"].errors == 0
    assert by_id["a"].last_result == "error"
    assert by_id["b"].last_result == "ok"
