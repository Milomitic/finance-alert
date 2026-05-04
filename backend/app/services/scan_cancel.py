"""In-process cancel registry for running scans.

When the user clicks "Stop" in the UI, the API endpoint registers a cancel
request for the live ScanRun id. The scan_universe loop checks the registry
between iterations and bails out cleanly (so partial state stays consistent
and the row gets marked 'failed' with a clear message).

Trade-offs:
- In-memory only: a backend restart wipes pending cancels. Acceptable because
  a restart also kills the worker — the orphan-cleanup hook in app startup
  marks any 'running' row as failed regardless.
- Single-process only: if the app ever runs multi-worker, cancels would have
  to migrate to a shared store (Redis, DB row flag). Today uvicorn runs single-
  worker so a Python set is enough.

The check is `O(1)` and called every `progress_every` iterations of
`scan_universe`, so the overhead is negligible.
"""
from __future__ import annotations

from threading import Lock

# Set of ScanRun.id values for which a cancel has been requested.
_REQUESTS: set[int] = set()
_LOCK = Lock()


def request_cancel(run_id: int) -> None:
    """Mark `run_id` as cancel-requested. Idempotent."""
    with _LOCK:
        _REQUESTS.add(run_id)


def is_cancel_requested(run_id: int) -> bool:
    """Cheap O(1) check called from the scan loop."""
    with _LOCK:
        return run_id in _REQUESTS


def clear(run_id: int) -> None:
    """Remove the request flag (called by the runner once it has bailed,
    so the same id can theoretically be reused later without lingering state)."""
    with _LOCK:
        _REQUESTS.discard(run_id)


def pending_count() -> int:
    """Diagnostics."""
    with _LOCK:
        return len(_REQUESTS)
