"""Single-scan mutex. All scans (manual API, scheduled cron, boot catch-up) run
in-process as threads against one single-writer SQLite DB. Two concurrent scans
both run fetch_and_upsert -> 'database is locked'. The mutex guarantees at most
one scan at a time; extra triggers skip instead of piling on."""
from unittest.mock import patch

from app.services import scan_lock


def test_only_one_slot_holder():
    with scan_lock.scan_slot() as first:
        assert first is True
        with scan_lock.scan_slot() as second:
            assert second is False  # already held -> caller must skip


def test_is_running_reflects_slot():
    assert scan_lock.is_running() is False
    with scan_lock.scan_slot() as acq:
        assert acq is True
        assert scan_lock.is_running() is True
    assert scan_lock.is_running() is False  # released on normal exit


def test_slot_released_after_exception():
    try:
        with scan_lock.scan_slot() as acq:
            assert acq is True
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert scan_lock.is_running() is False  # released even on error


def test_run_scan_alerts_skips_when_a_scan_is_running():
    """The cron / boot-catch-up entry point must no-op when a scan already holds
    the slot — never start a second concurrent fetch+upsert."""
    from app.scheduler.jobs import scan_alerts as job

    with scan_lock.scan_slot() as held:
        assert held is True
        with patch.object(job, "fetch_and_upsert") as fetch, \
                patch.object(job, "run_tracked_scan") as run:
            job.run_scan_alerts(trigger="cron")
            fetch.assert_not_called()
            run.assert_not_called()
