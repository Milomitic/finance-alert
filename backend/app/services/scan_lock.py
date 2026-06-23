"""Process-global single-scan guard.

All scans run IN-PROCESS as threads on one uvicorn process against a single
SQLite file: the manual API scan (`_run_scan_in_background`), the scheduled
nightly/EU-close scans, and the boot catch-up — all funnel through
`run_scan_alerts` or `_run_scan_in_background`. SQLite is single-writer, and a
scan is a multi-minute writer (chunked `fetch_and_upsert` + recompute). Two
scans at once hammer the write lock and surface `sqlite3.OperationalError:
database is locked`.

This non-reentrant lock ensures at most ONE scan runs at a time. Extra triggers
(e.g. the boot catch-up firing while the user already kicked a manual scan)
SKIP instead of piling on. The lock lives only in memory, so a process restart
clears it — there is no persistent stuck state.
"""
import threading
from collections.abc import Iterator
from contextlib import contextmanager

_LOCK = threading.Lock()


def is_running() -> bool:
    """Best-effort: True if a scan currently holds the slot. Racy by nature
    (a scan may start/finish right after the check) — use only for advisory
    pre-checks / status; the authoritative guard is `scan_slot()`."""
    if _LOCK.acquire(blocking=False):
        _LOCK.release()
        return False
    return True


@contextmanager
def scan_slot() -> Iterator[bool]:
    """Non-blocking acquire of the single-scan slot.

    Yields True if this caller now OWNS the slot and must run the scan; yields
    False if a scan is already running and the caller should skip. Releases the
    slot on exit (including on exception) only if it was acquired here.

        with scan_slot() as acquired:
            if not acquired:
                return            # another scan is already running
            ...run the scan...
    """
    acquired = _LOCK.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            _LOCK.release()
