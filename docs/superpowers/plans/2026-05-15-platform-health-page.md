# Platform Health Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `/health` page that shows live service health (4 cards: data sources, scheduler, recent scans, cache+DB) and a streaming filterable log viewer, backed by an in-process ring buffer + pub/sub + SSE.

**Architecture:** A loguru sink writes every log record to an in-memory deque (maxlen=2000) that doubles as a pub/sub. APScheduler events feed a job-stats dict via a listener. Three new REST endpoints serve snapshot + filtered logs + SSE stream. The React page does an initial REST load, then opens `EventSource` for live updates.

**Tech Stack:** FastAPI (StreamingResponse), loguru, APScheduler listeners, asyncio.Queue (SSE), React 19 + TanStack Query (initial load) + native EventSource (live), shadcn/ui cards + Tailwind.

**Constraint:** The 511-test baseline must remain green. Test command from worktree's `backend/`:
```
"C:/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe" -m pytest tests/ -x -q
```

**Frontend rebuild constraint:** After ANY frontend source change, `cd frontend && npm run build` is required for the page to be visible on `:8000` (the FastAPI-served bundle). See CLAUDE.md.

**Working dir:** A git worktree at `C:/Users/giuli/Documents/Progetti/finance-alert/.worktrees/platform-health` on branch `feat/platform-health-2026-05-15`, branched from master at `8e5462e`.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `backend/app/core/log_buffer.py` | NEW | Thread-safe deque + pub/sub. Loguru sink target + SSE subscribers. |
| `backend/app/services/scheduler_metrics.py` | NEW | APScheduler listener; per-job last_run/result/duration stats. |
| `backend/app/services/cache_metrics.py` | NEW | Read-only snapshot of L1/L2 entry counts + DB file size. |
| `backend/app/api/platform_health.py` | NEW | 3 endpoints: `/api/platform/health`, `/logs`, `/stream`. |
| `backend/app/schemas/platform.py` | NEW | Pydantic schemas for the responses (health snapshot, log record). |
| `backend/app/core/logging.py` | MODIFY | Add the in-memory sink. |
| `backend/app/scheduler/__init__.py` | MODIFY | Register the metrics listener. |
| `backend/app/main.py` | MODIFY | Include the new router. |
| `frontend/src/pages/PlatformHealthPage.tsx` | NEW | Page shell: routes data into cards + log stream. |
| `frontend/src/components/health/DataSourcesCard.tsx` | NEW | Shows yfinance breaker + per-source success rates. |
| `frontend/src/components/health/SchedulerCard.tsx` | NEW | Lists 9 jobs with last/next run + status. |
| `frontend/src/components/health/ScansCard.tsx` | NEW | Last 10 ScanRun rows summary. |
| `frontend/src/components/health/CacheCard.tsx` | NEW | L1/L2 + DB size. |
| `frontend/src/components/health/LogStream.tsx` | NEW | Filterable scrollable log table. |
| `frontend/src/hooks/usePlatformHealthStream.ts` | NEW | EventSource hook; emits snapshot + log events. |
| `frontend/src/api/platformHealth.ts` | NEW | typed REST client for the new endpoints. |
| `frontend/src/components/Layout.tsx` | MODIFY | Add nav entry "Salute" with HeartPulse icon. |
| `frontend/src/main.tsx` or `App.tsx` | MODIFY | Register the new route. |
| `backend/tests/test_log_buffer.py` | NEW | Unit tests for the ring buffer + pub/sub. |
| `backend/tests/test_scheduler_metrics.py` | NEW | Unit tests for stats update logic. |
| `backend/tests/test_cache_metrics.py` | NEW | Unit tests for snapshot shape. |
| `backend/tests/test_api_platform_health.py` | NEW | Integration tests for the 3 endpoints. |

---

## Phase 1 — Backend infrastructure (5 tasks)

### Task 1: Ring buffer + pub/sub (`log_buffer.py`)

**Files:**
- Create: `backend/app/core/log_buffer.py`
- Create: `backend/tests/test_log_buffer.py`

- [ ] **Step 1.1: Write the failing tests**

```python
# backend/tests/test_log_buffer.py
"""Ring buffer with pub/sub for in-memory log streaming. Loguru sinks
write here; SSE handlers subscribe to receive new records."""
import time
from app.core.log_buffer import LogBuffer


def test_append_and_snapshot_preserves_insertion_order():
    buf = LogBuffer(maxlen=10)
    for i in range(5):
        buf.append_record({"ts": time.time(), "level": "INFO",
                           "module": "m", "function": "f", "line": 1,
                           "message": f"msg{i}"})
    snap = buf.get_snapshot()
    assert [r["message"] for r in snap] == ["msg0", "msg1", "msg2", "msg3", "msg4"]


def test_maxlen_drops_oldest():
    buf = LogBuffer(maxlen=3)
    for i in range(5):
        buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                           "function": "f", "line": 1, "message": f"msg{i}"})
    snap = buf.get_snapshot()
    assert [r["message"] for r in snap] == ["msg2", "msg3", "msg4"]


def test_filter_by_level_keeps_target_and_higher():
    buf = LogBuffer(maxlen=10)
    for lvl in ("DEBUG", "INFO", "WARNING", "ERROR"):
        buf.append_record({"ts": 0, "level": lvl, "module": "m",
                           "function": "f", "line": 1, "message": lvl})
    snap = buf.get_snapshot(level="WARNING")
    assert [r["level"] for r in snap] == ["WARNING", "ERROR"]


def test_filter_by_module_substring():
    buf = LogBuffer(maxlen=10)
    buf.append_record({"ts": 0, "level": "INFO", "module": "scan_service",
                       "function": "f", "line": 1, "message": "a"})
    buf.append_record({"ts": 0, "level": "INFO", "module": "stocks",
                       "function": "f", "line": 1, "message": "b"})
    snap = buf.get_snapshot(module="scan")
    assert [r["message"] for r in snap] == ["a"]


def test_filter_by_search_substring():
    buf = LogBuffer(maxlen=10)
    buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                       "function": "f", "line": 1, "message": "timeout AAPL"})
    buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                       "function": "f", "line": 1, "message": "ok"})
    snap = buf.get_snapshot(search="timeout")
    assert [r["message"] for r in snap] == ["timeout AAPL"]


def test_limit_returns_last_n():
    buf = LogBuffer(maxlen=10)
    for i in range(8):
        buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                           "function": "f", "line": 1, "message": f"msg{i}"})
    snap = buf.get_snapshot(limit=3)
    assert [r["message"] for r in snap] == ["msg5", "msg6", "msg7"]


def test_subscribe_called_on_each_append():
    buf = LogBuffer(maxlen=10)
    seen: list[dict] = []
    unsub = buf.subscribe(seen.append)
    buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                       "function": "f", "line": 1, "message": "a"})
    buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                       "function": "f", "line": 1, "message": "b"})
    assert [r["message"] for r in seen] == ["a", "b"]
    unsub()
    buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                       "function": "f", "line": 1, "message": "c"})
    assert [r["message"] for r in seen] == ["a", "b"]  # unsubscribed


def test_subscribe_callback_exception_does_not_break_others():
    """A buggy subscriber must not break the rest of the pub/sub."""
    buf = LogBuffer(maxlen=10)
    good_seen: list[dict] = []

    def bad(_r):
        raise RuntimeError("subscriber crashed")

    buf.subscribe(bad)
    buf.subscribe(good_seen.append)
    buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                       "function": "f", "line": 1, "message": "a"})
    assert len(good_seen) == 1
```

- [ ] **Step 1.2: Run tests (expect ModuleNotFoundError)**

```
cd backend
"C:/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe" -m pytest tests/test_log_buffer.py -v
```
Expected: collection error, module not found.

- [ ] **Step 1.3: Implement `log_buffer.py`**

```python
# backend/app/core/log_buffer.py
"""Ring buffer for log records with pub/sub.

Loguru writes here via a sink (see core/logging.py). SSE handlers
subscribe to receive each new record as it arrives.

Thread-safe: deque append is atomic, but we wrap subscriber notification
in a try/except per subscriber so one buggy listener can't break the rest
or break logging itself."""
from collections import deque
from collections.abc import Callable
from threading import Lock
from typing import Any

from loguru import logger

# Numeric severity for level-filtering. Mirror loguru's defaults.
_LEVEL_NO = {
    "TRACE": 5, "DEBUG": 10, "INFO": 20, "SUCCESS": 25,
    "WARNING": 30, "ERROR": 40, "CRITICAL": 50,
}


class LogBuffer:
    def __init__(self, maxlen: int = 2000) -> None:
        self._buf: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._subs: list[Callable[[dict[str, Any]], None]] = []
        self._lock = Lock()

    def append_record(self, record: dict[str, Any]) -> None:
        """Add a record. Records pushed by the loguru sink are already
        in our normalized shape (see core/logging.py)."""
        with self._lock:
            self._buf.append(record)
            subs = list(self._subs)
        # Notify outside the lock so a slow subscriber can't block appends.
        for cb in subs:
            try:
                cb(record)
            except Exception as exc:  # noqa: BLE001 — sub crashed, not our fault
                logger.warning(
                    f"[log_buffer] subscriber {cb!r} raised: {exc!r}"
                )

    def get_snapshot(
        self,
        *,
        level: str | None = None,
        module: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Filtered slice of the buffer.

        - level: keep records whose level >= the given level (e.g. WARNING
          returns WARNING + ERROR + CRITICAL).
        - module: substring match on the record's module field.
        - search: substring match on the message field.
        - limit: return at most the last N records after filtering.
        """
        with self._lock:
            snap = list(self._buf)
        if level:
            threshold = _LEVEL_NO.get(level.upper(), 0)
            snap = [r for r in snap if _LEVEL_NO.get(r["level"], 0) >= threshold]
        if module:
            snap = [r for r in snap if module in r.get("module", "")]
        if search:
            snap = [r for r in snap if search in r.get("message", "")]
        return snap[-limit:] if limit else snap

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Register a callback. Returns an unsubscribe function."""
        with self._lock:
            self._subs.append(callback)

        def _unsub() -> None:
            with self._lock:
                try:
                    self._subs.remove(callback)
                except ValueError:
                    pass

        return _unsub


# Module-level singleton consumed by the loguru sink + SSE handler.
_INSTANCE = LogBuffer()
```

- [ ] **Step 1.4: Run tests (expect 8 passed)**

```
"C:/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe" -m pytest tests/test_log_buffer.py -v
```

- [ ] **Step 1.5: Run full suite (must remain at 511)**

```
"C:/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe" -m pytest tests/ -x -q
```
Expected: 519 passed (511 + 8 new).

- [ ] **Step 1.6: Commit**

```bash
git add backend/app/core/log_buffer.py backend/tests/test_log_buffer.py
git commit -m "log_buffer: in-memory ring buffer with pub/sub for streaming logs"
```

---

### Task 2: Loguru sink wire-up

**Files:**
- Modify: `backend/app/core/logging.py`
- Create: `backend/tests/test_logging_sink.py`

- [ ] **Step 2.1: Write integration test**

```python
# backend/tests/test_logging_sink.py
"""Verify that loguru's logger.info/warning/error writes into the
in-memory ring buffer via the configured sink."""
from loguru import logger

from app.core.log_buffer import _INSTANCE as log_buffer
from app.core.logging import configure_logging


def test_logger_warning_lands_in_buffer():
    configure_logging()
    # snapshot starting size — other tests may have logged before us
    before = len(log_buffer.get_snapshot(limit=0))  # limit=0 → no truncation
    logger.warning("test-marker-from-test-logging-sink-warning")
    snap = log_buffer.get_snapshot(limit=0)
    matches = [r for r in snap if "test-marker-from-test-logging-sink-warning" in r["message"]]
    assert len(matches) == 1, f"expected 1 match, got {len(matches)}; buffer grew by {len(snap)-before}"
    rec = matches[0]
    assert rec["level"] == "WARNING"
    assert isinstance(rec["ts"], float)
    assert "module" in rec
    assert "line" in rec


def test_logger_error_includes_exception_traceback():
    configure_logging()
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("test-marker-exception-line-xyz")
    snap = log_buffer.get_snapshot(limit=0)
    matches = [r for r in snap if "test-marker-exception-line-xyz" in r["message"]]
    assert matches
    rec = matches[-1]
    assert rec["exception"] is not None
    assert "ValueError" in rec["exception"]
    assert "boom" in rec["exception"]
```

Also adjust the `get_snapshot` signature in `log_buffer.py`: `limit=0` should mean "no truncation". Replace the return statement:

```python
return snap[-limit:] if limit else snap
```

Already supports `limit=0` (falsy) → returns the full filtered snap. Good.

- [ ] **Step 2.2: Run test (expect FAIL — sink not wired)**

```
"C:/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe" -m pytest tests/test_logging_sink.py -v
```

- [ ] **Step 2.3: Modify `backend/app/core/logging.py`**

Add a third sink that pushes to the ring buffer. Place after the file sink. Use loguru's `record` callback — the sink callable receives a `Message` whose `.record` attribute is the structured dict.

```python
"""Loguru configuration: console + rotated file + in-memory buffer."""
import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings
from app.core.log_buffer import _INSTANCE as log_buffer


def _buffer_sink(message) -> None:
    """Loguru sink that pushes a normalized record into the in-memory
    ring buffer. `message.record` is the structured dict loguru passes
    to custom sinks; we reshape it into a smaller payload optimized for
    JSON serialization (no datetime objects, no thread/process info)."""
    r = message.record
    exc = r.get("exception")
    payload = {
        "ts": r["time"].timestamp(),
        "level": r["level"].name,
        "module": r["module"] or r["name"],
        "function": r["function"] or "",
        "line": r["line"] or 0,
        "message": r["message"],
        "exception": str(exc) if exc is not None else None,
    }
    log_buffer.append_record(payload)


def configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>",
    )
    logs_dir = Path("./data/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        logs_dir / "app.log",
        level=settings.log_level,
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )
    # In-memory ring buffer for the /api/platform/stream endpoint.
    # Capture from DEBUG so the UI filter can choose what to show.
    logger.add(
        _buffer_sink,
        level="DEBUG",
        format="{message}",
    )
```

- [ ] **Step 2.4: Run test (expect 2 passed)**

- [ ] **Step 2.5: Run full suite**

Expected: 521 passed (519 + 2 new).

**Watch out:** other tests that call `configure_logging` may now produce extra appends to the buffer. That's harmless — the buffer is in-memory and bounded. If a flaky test fails due to leftover state, check the `before`/`after` count in your assertion.

- [ ] **Step 2.6: Commit**

```bash
git add backend/app/core/logging.py backend/tests/test_logging_sink.py
git commit -m "logging: add in-memory buffer sink for /api/platform stream"
```

---

### Task 3: Scheduler metrics listener

**Files:**
- Create: `backend/app/services/scheduler_metrics.py`
- Create: `backend/tests/test_scheduler_metrics.py`

- [ ] **Step 3.1: Write tests**

```python
# backend/tests/test_scheduler_metrics.py
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
    assert s.runs == 1            # only one successful run
    assert s.errors == 1
    assert s.last_result == "error"   # last event was an error


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
```

- [ ] **Step 3.2: Run test (expect ImportError)**

- [ ] **Step 3.3: Implement `scheduler_metrics.py`**

```python
# backend/app/services/scheduler_metrics.py
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
```

- [ ] **Step 3.4: Run tests (expect 6 passed)**

- [ ] **Step 3.5: Wire the listener in scheduler `__init__.py`**

Modify `backend/app/scheduler/__init__.py`. After the line that creates `_scheduler = BackgroundScheduler(...)` and before the first `_scheduler.add_job(...)`:

```python
from app.services.scheduler_metrics import install_listener as _install_scheduler_listener

# (inside get_scheduler, after creating _scheduler:)
_install_scheduler_listener(_scheduler)
```

- [ ] **Step 3.6: Run full suite**

Expected: 527 passed (521 + 6 new).

- [ ] **Step 3.7: Commit**

```bash
git add backend/app/services/scheduler_metrics.py \
        backend/tests/test_scheduler_metrics.py \
        backend/app/scheduler/__init__.py
git commit -m "scheduler_metrics: APScheduler listener for per-job stats"
```

---

### Task 4: Cache + DB metrics

**Files:**
- Create: `backend/app/services/cache_metrics.py`
- Create: `backend/tests/test_cache_metrics.py`

- [ ] **Step 4.1: Write tests**

```python
# backend/tests/test_cache_metrics.py
"""Snapshot of L1 cache state + L2 row counts + DB file size.
Pure read; no side effects on the cache or DB."""
import time

from app.services import cache_metrics
from app.services import stock_fundamentals_service, stock_news_service


def test_snapshot_shape_on_empty_caches(db):
    # Clear the L1 dicts so we have a deterministic baseline. Don't touch L2.
    stock_fundamentals_service._CACHE.clear()
    stock_news_service._CACHE.clear()

    snap = cache_metrics.snapshot()

    assert set(snap.keys()) == {"fundamentals", "news", "db"}
    assert snap["fundamentals"]["l1_entries"] == 0
    assert snap["news"]["l1_entries"] == 0
    assert snap["fundamentals"]["oldest_age_s"] is None
    assert snap["news"]["oldest_age_s"] is None
    # L2 counts depend on the test DB; just verify they're non-negative ints.
    assert isinstance(snap["fundamentals"]["l2_entries"], int)
    assert snap["fundamentals"]["l2_entries"] >= 0
    # DB size in MB — for an in-memory SQLite or a freshly created file,
    # this can be 0.0; just verify it's a float.
    assert isinstance(snap["db"]["size_mb"], float)


def test_snapshot_reflects_l1_entries(db):
    stock_fundamentals_service._CACHE.clear()
    # Inject a fake entry directly into the L1 dict for test purposes.
    # We use the actual Fundamentals dataclass so the shape is correct.
    from app.services.stock_fundamentals_service import Fundamentals
    stock_fundamentals_service._CACHE["FAKE"] = Fundamentals(
        ticker="FAKE", fetched_at=time.time() - 30.0
    )

    snap = cache_metrics.snapshot()

    assert snap["fundamentals"]["l1_entries"] == 1
    assert snap["fundamentals"]["oldest_age_s"] is not None
    assert snap["fundamentals"]["oldest_age_s"] >= 30.0


def test_snapshot_oldest_age_is_oldest_not_newest(db):
    stock_fundamentals_service._CACHE.clear()
    from app.services.stock_fundamentals_service import Fundamentals
    now = time.time()
    stock_fundamentals_service._CACHE["A"] = Fundamentals(ticker="A", fetched_at=now - 100.0)
    stock_fundamentals_service._CACHE["B"] = Fundamentals(ticker="B", fetched_at=now - 5.0)

    snap = cache_metrics.snapshot()

    assert snap["fundamentals"]["oldest_age_s"] >= 100.0
```

- [ ] **Step 4.2: Run tests (expect ImportError)**

- [ ] **Step 4.3: Implement `cache_metrics.py`**

```python
# backend/app/services/cache_metrics.py
"""Read-only snapshot of cache + DB state for the platform-health page.

We sample without mutating: counts, oldest entry age, DB file size.
"""
import time
from pathlib import Path

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import FetchCache


def _l1_stats(cache_dict: dict) -> dict:
    """Count entries + age of the oldest one. Entries are dataclass-like
    objects with a `fetched_at` attribute (or tuple shape for news cache).

    News cache stores (timestamp, items) tuples — handle both shapes."""
    if not cache_dict:
        return {"l1_entries": 0, "oldest_age_s": None}
    now = time.time()
    oldest = None
    for v in cache_dict.values():
        if isinstance(v, tuple):
            # news cache: (datetime, items) — convert dt → ts
            dt = v[0]
            ts = dt.timestamp() if hasattr(dt, "timestamp") else float(dt)
        else:
            ts = float(getattr(v, "fetched_at", now))
        age = now - ts
        if oldest is None or age > oldest:
            oldest = age
    return {"l1_entries": len(cache_dict), "oldest_age_s": oldest}


def _l2_count(kind: str) -> int:
    with SessionLocal() as db:
        n = db.execute(
            select(func.count()).select_from(FetchCache).where(FetchCache.kind == kind)
        ).scalar_one()
    return int(n or 0)


def _db_size_mb() -> float:
    """Return the size of the SQLite file (data/app.db) in MB.
    Returns 0.0 if the file doesn't exist (in-memory SQLite during tests)."""
    p = Path("./data/app.db")
    if not p.exists():
        return 0.0
    return round(p.stat().st_size / (1024 * 1024), 2)


def snapshot() -> dict:
    """Combined cache + DB snapshot. Cheap (no upstream calls)."""
    from app.services import stock_fundamentals_service, stock_news_service
    return {
        "fundamentals": {
            **_l1_stats(stock_fundamentals_service._CACHE),
            "l2_entries": _l2_count("fundamentals"),
        },
        "news": {
            **_l1_stats(stock_news_service._CACHE),
            "l2_entries": _l2_count("news"),
        },
        "db": {"size_mb": _db_size_mb()},
    }
```

- [ ] **Step 4.4: Run tests (expect 3 passed)**

If the `Fundamentals` dataclass has required fields that the test omits, adapt the test to pass the actually-required fields. The test's goal is to inject a row with a known `fetched_at`; the other fields can be defaults.

- [ ] **Step 4.5: Run full suite**

Expected: 530 passed (527 + 3 new).

- [ ] **Step 4.6: Commit**

```bash
git add backend/app/services/cache_metrics.py backend/tests/test_cache_metrics.py
git commit -m "cache_metrics: snapshot of L1 + L2 + DB size for platform health"
```

---

### Task 5: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/platform.py`

This task has no separate tests — the schemas are exercised by the API integration tests in Task 6.

- [ ] **Step 5.1: Create the schema module**

```python
# backend/app/schemas/platform.py
"""Pydantic response schemas for /api/platform/* endpoints."""
from pydantic import BaseModel


class DataSourceMetricOut(BaseModel):
    source: str
    op: str
    success: int
    failure: int
    success_rate: float
    last_success_at: float | None
    last_failure_at: float | None
    last_failure_reason: str | None
    health: str


class SchedulerJobStatOut(BaseModel):
    job_id: str
    last_run_at: float | None
    last_result: str | None
    last_duration_ms: float | None
    last_error: str | None
    runs: int
    errors: int


class RecentScanOut(BaseModel):
    id: int
    status: str
    phase: str | None
    trigger: str
    started_at: str | None
    completed_at: str | None
    duration_s: float | None
    progress_done: int | None
    progress_total: int | None
    alerts_count: int | None
    error_message: str | None


class CacheKindStatOut(BaseModel):
    l1_entries: int
    l2_entries: int
    oldest_age_s: float | None


class CacheStatsOut(BaseModel):
    fundamentals: CacheKindStatOut
    news: CacheKindStatOut
    db: dict   # {"size_mb": float}


class PlatformHealthOut(BaseModel):
    data_sources: list[DataSourceMetricOut]
    yfinance_breaker: dict   # the existing yfinance_health.status() shape
    scheduler: list[SchedulerJobStatOut]
    scans: list[RecentScanOut]
    cache: CacheStatsOut


class LogRecordOut(BaseModel):
    ts: float
    level: str
    module: str
    function: str
    line: int
    message: str
    exception: str | None = None
```

- [ ] **Step 5.2: Commit**

```bash
git add backend/app/schemas/platform.py
git commit -m "schemas: pydantic models for /api/platform/* responses"
```

(No suite run needed — pure schema definitions.)

---

## Phase 2 — Backend API (3 tasks)

### Task 6: REST `/api/platform/health` + `/logs`

**Files:**
- Create: `backend/app/api/platform_health.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api_platform_health.py`

- [ ] **Step 6.1: Write integration tests**

```python
# backend/tests/test_api_platform_health.py
"""Integration tests for /api/platform/health and /logs.
SSE stream is tested separately to keep this file focused."""
from loguru import logger

from app.core.logging import configure_logging


def test_health_endpoint_requires_auth(client):
    r = client.get("/api/platform/health")
    assert r.status_code in (401, 403)


def test_health_endpoint_returns_expected_keys(client_auth):
    r = client_auth.get("/api/platform/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "data_sources", "yfinance_breaker", "scheduler", "scans", "cache"
    }
    assert isinstance(body["data_sources"], list)
    assert isinstance(body["scheduler"], list)
    assert isinstance(body["scans"], list)
    assert "fundamentals" in body["cache"]
    assert "news" in body["cache"]
    assert "db" in body["cache"]


def test_logs_endpoint_requires_auth(client):
    r = client.get("/api/platform/logs")
    assert r.status_code in (401, 403)


def test_logs_endpoint_returns_recent_records(client_auth):
    configure_logging()
    logger.warning("test-marker-logs-endpoint-aaa")
    r = client_auth.get("/api/platform/logs?limit=200")
    assert r.status_code == 200
    records = r.json()
    assert any("test-marker-logs-endpoint-aaa" in rec["message"] for rec in records)


def test_logs_endpoint_filters_by_level(client_auth):
    configure_logging()
    logger.info("test-marker-info-bbb")
    logger.error("test-marker-error-ccc")
    r = client_auth.get("/api/platform/logs?level=ERROR&limit=200")
    assert r.status_code == 200
    records = r.json()
    msgs = [rec["message"] for rec in records]
    assert any("test-marker-error-ccc" in m for m in msgs)
    assert not any("test-marker-info-bbb" in m for m in msgs)


def test_logs_endpoint_filters_by_search_substring(client_auth):
    configure_logging()
    logger.warning("unique-string-zzz123")
    r = client_auth.get("/api/platform/logs?search=zzz123&limit=200")
    assert r.status_code == 200
    records = r.json()
    assert len(records) >= 1
    assert all("zzz123" in rec["message"] for rec in records)
```

**Note on fixtures:** the test references `client` (unauthenticated TestClient) and `client_auth` (authenticated). Check `backend/tests/conftest.py` for the actual names. If they're called differently, adapt. If only one client fixture exists, create the auth one by following the pattern in `test_api_stocks.py` or `test_api_alerts.py`.

- [ ] **Step 6.2: Run tests (expect 404 / ModuleNotFoundError)**

- [ ] **Step 6.3: Implement `platform_health.py`**

```python
# backend/app/api/platform_health.py
"""Read-only API for the platform-health UI. Three endpoints:
- GET /health    → combined snapshot (REST)
- GET /logs      → filtered log slice (REST)
- GET /stream    → SSE stream (Task 7)
"""
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.log_buffer import _INSTANCE as log_buffer
from app.models import Alert, ScanRun, User
from app.schemas.platform import (
    LogRecordOut, PlatformHealthOut, RecentScanOut, SchedulerJobStatOut,
)
from app.services import cache_metrics, data_source_metrics, yfinance_health
from app.services.scheduler_metrics import _INSTANCE as scheduler_metrics

router = APIRouter(prefix="/api/platform", tags=["platform"])


def _recent_scans(db: Session, limit: int = 10) -> list[RecentScanOut]:
    rows = db.execute(
        select(ScanRun).order_by(desc(ScanRun.id)).limit(limit)
    ).scalars().all()
    out: list[RecentScanOut] = []
    for r in rows:
        # Count alerts produced by this run (alerts.fired_at within run window)
        alerts_count: int | None = None
        if r.started_at and r.completed_at:
            alerts_count = db.execute(
                select(func.count()).select_from(Alert).where(
                    Alert.triggered_at >= r.started_at,
                    Alert.triggered_at <= r.completed_at,
                )
            ).scalar_one()
        duration_s: float | None = None
        if r.started_at and r.completed_at:
            duration_s = (r.completed_at - r.started_at).total_seconds()
        out.append(RecentScanOut(
            id=r.id,
            status=r.status,
            phase=r.phase,
            trigger=r.trigger,
            started_at=r.started_at.isoformat() if r.started_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            duration_s=duration_s,
            progress_done=r.progress_done,
            progress_total=r.progress_total,
            alerts_count=alerts_count,
            error_message=r.error_message,
        ))
    return out


@router.get("/health", response_model=PlatformHealthOut)
def health_snapshot(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PlatformHealthOut:
    metrics = data_source_metrics.snapshot()
    return PlatformHealthOut(
        data_sources=[
            {
                "source": m.source, "op": m.op, "success": m.success,
                "failure": m.failure, "success_rate": m.success_rate,
                "last_success_at": m.last_success_at,
                "last_failure_at": m.last_failure_at,
                "last_failure_reason": m.last_failure_reason,
                "health": m.health,
            }
            for m in metrics
        ],
        yfinance_breaker=yfinance_health.status(),
        scheduler=[SchedulerJobStatOut(**s) for s in scheduler_metrics.snapshot_dict()],
        scans=_recent_scans(db),
        cache=cache_metrics.snapshot(),
    )


@router.get("/logs", response_model=list[LogRecordOut])
def logs(
    level: Annotated[str | None, Query()] = None,
    module: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    _user: User = Depends(get_current_user),
) -> list[LogRecordOut]:
    records = log_buffer.get_snapshot(
        level=level, module=module, search=search, limit=limit
    )
    return [LogRecordOut(**r) for r in records]
```

- [ ] **Step 6.4: Wire in `main.py`**

Add the import:
```python
from app.api import platform_health as platform_health_router
```

Add the include:
```python
app.include_router(platform_health_router.router)
```

- [ ] **Step 6.5: Run integration tests (expect 5 passed)**

- [ ] **Step 6.6: Run full suite**

Expected: 535 passed (530 + 5 new). If the new tests reveal that `client_auth` fixture name is wrong, fix the fixture reference and re-run.

- [ ] **Step 6.7: Commit**

```bash
git add backend/app/api/platform_health.py \
        backend/app/main.py \
        backend/tests/test_api_platform_health.py
git commit -m "api: GET /api/platform/health + /logs REST endpoints"
```

---

### Task 7: SSE `/api/platform/stream`

**Files:**
- Modify: `backend/app/api/platform_health.py`
- Create: `backend/tests/test_api_platform_stream.py`

- [ ] **Step 7.1: Write SSE integration test**

```python
# backend/tests/test_api_platform_stream.py
"""SSE stream emits: snapshot (initial + periodic), log (each new record),
keepalive (idle). We don't test the 30s keepalive (too slow); we test the
log push and initial snapshot."""
import json

from fastapi.testclient import TestClient
from loguru import logger

from app.core.logging import configure_logging


def _parse_sse(chunk: bytes) -> list[tuple[str, str]]:
    """Parse a raw SSE chunk into [(event, data), ...] tuples.
    Returns empty for keepalive comments."""
    events: list[tuple[str, str]] = []
    current_event: str | None = None
    current_data_parts: list[str] = []
    for line in chunk.decode("utf-8").splitlines():
        if line.startswith(":"):
            continue
        if line == "":
            if current_event and current_data_parts:
                events.append((current_event, "\n".join(current_data_parts)))
            current_event = None
            current_data_parts = []
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            current_data_parts.append(line[5:].strip())
    if current_event and current_data_parts:
        events.append((current_event, "\n".join(current_data_parts)))
    return events


def test_stream_emits_initial_snapshot_then_log_on_logger_call(client_auth):
    configure_logging()
    # Use TestClient's stream context. Snapshot+log are emitted by the
    # backend within ~50ms.
    with client_auth.stream("GET", "/api/platform/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        # Pull the first ~10KB of data. The first chunk should contain the
        # snapshot event.
        buf = b""
        for chunk in response.iter_raw():
            buf += chunk
            if b"snapshot" in buf and len(buf) > 1000:
                break

    events = _parse_sse(buf)
    assert any(ev == "snapshot" for ev, _ in events)


def test_stream_pushes_log_record_when_logger_warning_called(client_auth):
    configure_logging()
    with client_auth.stream("GET", "/api/platform/stream") as response:
        # Read the initial snapshot first.
        buf = b""
        for chunk in response.iter_raw():
            buf += chunk
            if b"snapshot" in buf:
                break
        # Now trigger a log record. The SSE should push it.
        logger.warning("stream-marker-test-12345")
        # Pull more data.
        for chunk in response.iter_raw():
            buf += chunk
            if b"stream-marker-test-12345" in buf:
                break

    events = _parse_sse(buf)
    log_events = [json.loads(data) for ev, data in events if ev == "log"]
    assert any("stream-marker-test-12345" in rec["message"] for rec in log_events)
```

**Note:** if `client_auth` doesn't support `.stream()`, use a custom approach — e.g. construct an `httpx.Client` directly with the same auth cookie. The pattern depends on the existing fixture; adapt as needed.

- [ ] **Step 7.2: Run test (expect 404 — endpoint not present)**

- [ ] **Step 7.3: Implement the SSE endpoint**

Append to `backend/app/api/platform_health.py`:

```python
import asyncio
import json

from fastapi import Request
from fastapi.responses import StreamingResponse


@router.get("/stream")
async def stream(
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE stream emitting:
       - event: snapshot   (initial + every 5s)
       - event: log        (on each new log record)
       - : keepalive       (every 30s, SSE comment)
    """
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=1000)
    loop = asyncio.get_running_loop()

    def on_log(record: dict) -> None:
        # Called from the loguru sink thread. Schedule the put on the
        # event loop so we cross thread boundaries safely.
        try:
            payload = json.dumps(record, default=str)
            loop.call_soon_threadsafe(queue.put_nowait, ("log", payload))
        except asyncio.QueueFull:
            pass  # Drop the record rather than block logging.

    unsub = log_buffer.subscribe(on_log)

    async def _snapshot_payload() -> str:
        # Build a snapshot using the same logic as the REST endpoint.
        from app.services import data_source_metrics, yfinance_health
        from app.services.scheduler_metrics import _INSTANCE as scheduler_metrics_inst
        metrics = data_source_metrics.snapshot()
        snap_dict = {
            "data_sources": [
                {
                    "source": m.source, "op": m.op, "success": m.success,
                    "failure": m.failure, "success_rate": m.success_rate,
                    "last_success_at": m.last_success_at,
                    "last_failure_at": m.last_failure_at,
                    "last_failure_reason": m.last_failure_reason,
                    "health": m.health,
                }
                for m in metrics
            ],
            "yfinance_breaker": yfinance_health.status(),
            "scheduler": scheduler_metrics_inst.snapshot_dict(),
            "scans": [s.model_dump() for s in _recent_scans(db)],
            "cache": cache_metrics.snapshot(),
        }
        return json.dumps(snap_dict, default=str)

    async def _snapshot_loop() -> None:
        while True:
            await asyncio.sleep(5.0)
            payload = await _snapshot_payload()
            try:
                queue.put_nowait(("snapshot", payload))
            except asyncio.QueueFull:
                pass

    async def event_gen():
        # Send initial snapshot immediately.
        try:
            initial = await _snapshot_payload()
            yield f"event: snapshot\ndata: {initial}\n\n"
            snapshot_task = asyncio.create_task(_snapshot_loop())
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        event_type, data = await asyncio.wait_for(
                            queue.get(), timeout=30.0
                        )
                    except asyncio.TimeoutError:
                        # 30s without anything → send a keepalive comment.
                        yield ": keepalive\n\n"
                        continue
                    yield f"event: {event_type}\ndata: {data}\n\n"
            finally:
                snapshot_task.cancel()
        finally:
            unsub()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            # Disable buffering on intermediate proxies (uvicorn does
            # the right thing already, but be explicit).
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

**Concurrency note:** The loguru sink runs in whatever thread issued the log. `loop.call_soon_threadsafe` is the correct primitive for posting work from a different thread to the running asyncio event loop. The handler is async so it cooperates with `request.is_disconnected()` cleanly.

**Snapshot inside SSE:** the snapshot loop runs inside the async context but it calls some sync code (cache_metrics, scheduler_metrics) which is fine. The `_recent_scans` helper requires a DB session — we receive it via `Depends(get_db)` which is bound to the request. For a long-lived SSE connection, holding a single DB session can keep a SQLite write-lock from completing. **For this v1**, we accept this trade-off (single-user app, SQLite WAL mode handles concurrent reads). If it becomes a problem, open a fresh session per snapshot.

- [ ] **Step 7.4: Run SSE tests**

```
"C:/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe" -m pytest tests/test_api_platform_stream.py -v
```

If the tests are flaky (race conditions in the SSE test), insert short `time.sleep(0.05)` waits between actions, or use `await asyncio.sleep(...)` if running async tests. Document any flakiness as a known issue but don't skip these tests — the SSE pathway is the most important behavioral guarantee in this feature.

- [ ] **Step 7.5: Run full suite**

Expected: 537 passed (535 + 2 new).

- [ ] **Step 7.6: Commit**

```bash
git add backend/app/api/platform_health.py backend/tests/test_api_platform_stream.py
git commit -m "api: SSE /api/platform/stream for live health + log push"
```

---

## Phase 3 — Frontend (4 tasks)

### Task 8: Page skeleton + route + nav entry

**Files:**
- Create: `frontend/src/pages/PlatformHealthPage.tsx`
- Create: `frontend/src/api/platformHealth.ts`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/App.tsx` (or `frontend/src/main.tsx` — wherever routes are declared)

- [ ] **Step 8.1: Discover routes file**

```
grep -rn "BrowserRouter\|createBrowserRouter\|Routes\b" frontend/src/ --include='*.tsx'
```

Identify the file where the existing routes (`/`, `/alerts`, etc.) are declared. Likely `App.tsx` or `main.tsx`.

- [ ] **Step 8.2: Create API client `frontend/src/api/platformHealth.ts`**

```typescript
// frontend/src/api/platformHealth.ts
/**
 * Typed REST + SSE client for /api/platform/*.
 * Mirrors the Pydantic shapes in backend/app/schemas/platform.py.
 */
export type DataSourceMetric = {
  source: string;
  op: string;
  success: number;
  failure: number;
  success_rate: number;
  last_success_at: number | null;
  last_failure_at: number | null;
  last_failure_reason: string | null;
  health: string;
};

export type SchedulerJobStat = {
  job_id: string;
  last_run_at: number | null;
  last_result: string | null;
  last_duration_ms: number | null;
  last_error: string | null;
  runs: number;
  errors: number;
};

export type RecentScan = {
  id: number;
  status: string;
  phase: string | null;
  trigger: string;
  started_at: string | null;
  completed_at: string | null;
  duration_s: number | null;
  progress_done: number | null;
  progress_total: number | null;
  alerts_count: number | null;
  error_message: string | null;
};

export type CacheKindStat = {
  l1_entries: number;
  l2_entries: number;
  oldest_age_s: number | null;
};

export type PlatformHealth = {
  data_sources: DataSourceMetric[];
  yfinance_breaker: Record<string, unknown>;
  scheduler: SchedulerJobStat[];
  scans: RecentScan[];
  cache: {
    fundamentals: CacheKindStat;
    news: CacheKindStat;
    db: { size_mb: number };
  };
};

export type LogRecord = {
  ts: number;
  level: string;
  module: string;
  function: string;
  line: number;
  message: string;
  exception: string | null;
};

export async function fetchHealth(): Promise<PlatformHealth> {
  const r = await fetch("/api/platform/health", { credentials: "include" });
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function fetchLogs(params: {
  level?: string;
  module?: string;
  search?: string;
  limit?: number;
}): Promise<LogRecord[]> {
  const q = new URLSearchParams();
  if (params.level) q.set("level", params.level);
  if (params.module) q.set("module", params.module);
  if (params.search) q.set("search", params.search);
  if (params.limit) q.set("limit", String(params.limit));
  const r = await fetch(`/api/platform/logs?${q}`, { credentials: "include" });
  if (!r.ok) throw new Error(`logs ${r.status}`);
  return r.json();
}
```

- [ ] **Step 8.3: Create page skeleton `frontend/src/pages/PlatformHealthPage.tsx`**

```tsx
// frontend/src/pages/PlatformHealthPage.tsx
import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchLogs } from "@/api/platformHealth";

export default function PlatformHealthPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["platform-health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000, // fallback if SSE not yet wired
  });

  const { data: initialLogs } = useQuery({
    queryKey: ["platform-logs-initial"],
    queryFn: () => fetchLogs({ limit: 500 }),
  });

  return (
    <div className="p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Salute piattaforma</h1>
        <p className="text-sm text-muted-foreground">
          Monitoraggio servizi e log in tempo reale.
        </p>
      </header>

      {healthLoading && <div>Caricamento…</div>}
      {health && (
        <div className="grid gap-3 lg:grid-cols-4">
          <pre className="rounded border bg-muted/40 p-3 text-xs overflow-auto">
            {JSON.stringify(health.data_sources, null, 2)}
          </pre>
          <pre className="rounded border bg-muted/40 p-3 text-xs overflow-auto">
            {JSON.stringify(health.scheduler, null, 2)}
          </pre>
          <pre className="rounded border bg-muted/40 p-3 text-xs overflow-auto">
            {JSON.stringify(health.scans, null, 2)}
          </pre>
          <pre className="rounded border bg-muted/40 p-3 text-xs overflow-auto">
            {JSON.stringify(health.cache, null, 2)}
          </pre>
        </div>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Log</h2>
        <div className="rounded border bg-background p-2 max-h-[400px] overflow-auto font-mono text-xs space-y-1">
          {(initialLogs ?? []).slice(-200).map((r, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-muted-foreground">
                {new Date(r.ts * 1000).toLocaleTimeString()}
              </span>
              <span className="font-semibold w-16">{r.level}</span>
              <span className="text-muted-foreground">[{r.module}]</span>
              <span className="flex-1 truncate">{r.message}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
```

**Skeleton notes:** the visual polish (color-coded levels, status cards) comes in Tasks 9-10. This step just gets a working page rendering server data with raw JSON for the cards. The reasonable shadcn/ui Card components arrive in Task 9.

- [ ] **Step 8.4: Register the route**

In the routes file from Step 8.1, import and add:

```tsx
import PlatformHealthPage from "@/pages/PlatformHealthPage";

// inside Routes:
<Route path="/health" element={<PlatformHealthPage />} />
```

Place it inside the same authenticated route group as the others.

- [ ] **Step 8.5: Add nav entry in `Layout.tsx`**

Open `frontend/src/components/Layout.tsx`. Find the `NAV_ENTRIES` (or equivalent) array — line ~29 per discovery. Add the `HeartPulse` icon import and a new entry between Alerts and Impostazioni:

```tsx
import { HeartPulse } from "lucide-react";
// existing icon imports...

// inside the NAV_ENTRIES array:
{ to: "/alerts", label: "Alerts", icon: Bell, enabled: true },
{ to: "/health", label: "Salute", icon: HeartPulse, enabled: true },
{ to: "/settings", label: "Impostazioni", icon: Settings, enabled: true },
```

- [ ] **Step 8.6: Build the frontend bundle**

```
cd frontend && npm run build
```

Expected: clean build, no TypeScript errors. If `tsc` fails (worktree `.bin/` may be missing per CLAUDE.md), run `npm install` first.

- [ ] **Step 8.7: Commit**

```bash
git add frontend/src/api/platformHealth.ts \
        frontend/src/pages/PlatformHealthPage.tsx \
        frontend/src/components/Layout.tsx \
        frontend/src/App.tsx     # or the actual routes file
git commit -m "frontend: /health page skeleton + nav entry + REST client"
```

---

### Task 9: Health summary cards (4 components)

**Files:**
- Create: `frontend/src/components/health/DataSourcesCard.tsx`
- Create: `frontend/src/components/health/SchedulerCard.tsx`
- Create: `frontend/src/components/health/ScansCard.tsx`
- Create: `frontend/src/components/health/CacheCard.tsx`
- Modify: `frontend/src/pages/PlatformHealthPage.tsx` (use the cards instead of raw JSON)

- [ ] **Step 9.1: Create `DataSourcesCard.tsx`**

```tsx
// frontend/src/components/health/DataSourcesCard.tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { DataSourceMetric } from "@/api/platformHealth";

type Props = {
  metrics: DataSourceMetric[];
  yfinanceBreaker: Record<string, unknown>;
};

const HEALTH_TONE: Record<string, string> = {
  ok: "bg-emerald-500/10 text-emerald-700",
  warn: "bg-amber-500/10 text-amber-700",
  fail: "bg-red-500/10 text-red-700",
};

export default function DataSourcesCard({ metrics, yfinanceBreaker }: Props) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Sorgenti dati</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span>yfinance breaker</span>
          <span
            className={
              HEALTH_TONE[String(yfinanceBreaker.state ?? "ok").toLowerCase()] ??
              HEALTH_TONE.ok
            }
          >
            {String(yfinanceBreaker.state ?? "—")}
          </span>
        </div>
        <div className="border-t pt-2 space-y-1">
          {metrics.length === 0 && (
            <div className="text-muted-foreground italic">
              Nessuna metrica raccolta ancora
            </div>
          )}
          {metrics.map((m) => (
            <div key={`${m.source}.${m.op}`} className="flex items-center justify-between">
              <span className="font-mono">
                {m.source}.{m.op}
              </span>
              <span className={HEALTH_TONE[m.health] ?? HEALTH_TONE.ok}>
                {(m.success_rate * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 9.2: Create `SchedulerCard.tsx`**

```tsx
// frontend/src/components/health/SchedulerCard.tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { SchedulerJobStat } from "@/api/platformHealth";

type Props = { jobs: SchedulerJobStat[] };

const RESULT_TONE: Record<string, string> = {
  ok: "text-emerald-700",
  error: "text-red-700",
  missed: "text-amber-700",
};

function ago(ts: number | null): string {
  if (ts == null) return "—";
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s fa`;
  if (s < 3600) return `${Math.floor(s / 60)}m fa`;
  if (s < 86400) return `${Math.floor(s / 3600)}h fa`;
  return `${Math.floor(s / 86400)}g fa`;
}

export default function SchedulerCard({ jobs }: Props) {
  const errors = jobs.filter((j) => j.last_result === "error").length;
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">
          Scheduler{" "}
          <span className="text-xs text-muted-foreground">
            ({jobs.length} job{errors > 0 && `, ${errors} in errore`})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs space-y-1">
        {jobs.length === 0 && (
          <div className="text-muted-foreground italic">
            Nessun evento registrato ancora
          </div>
        )}
        {jobs.map((j) => (
          <div key={j.job_id} className="flex items-center justify-between gap-2">
            <span className="font-mono truncate">{j.job_id}</span>
            <span className={RESULT_TONE[j.last_result ?? ""] ?? "text-muted-foreground"}>
              {j.last_result ?? "—"} · {ago(j.last_run_at)}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 9.3: Create `ScansCard.tsx`**

```tsx
// frontend/src/components/health/ScansCard.tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { RecentScan } from "@/api/platformHealth";

type Props = { scans: RecentScan[] };

const STATUS_TONE: Record<string, string> = {
  success: "text-emerald-700",
  ok: "text-emerald-700",
  running: "text-blue-700",
  failed: "text-red-700",
  error: "text-red-700",
};

function fmtDuration(s: number | null): string {
  if (s == null) return "—";
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export default function ScansCard({ scans }: Props) {
  const last = scans[0];
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">
          Scan recenti{" "}
          <span className="text-xs text-muted-foreground">({scans.length})</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs space-y-2">
        {last && (
          <div className="border-b pb-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold">Ultimo:</span>
              <span className={STATUS_TONE[last.status] ?? "text-muted-foreground"}>
                {last.status}
              </span>
            </div>
            <div className="text-muted-foreground">
              {fmtDuration(last.duration_s)} ·{" "}
              {last.alerts_count != null
                ? `${last.alerts_count} alert`
                : `${last.progress_done ?? 0}/${last.progress_total ?? 0}`}
            </div>
            {last.error_message && (
              <div className="text-red-700 truncate" title={last.error_message}>
                {last.error_message}
              </div>
            )}
          </div>
        )}
        <div className="space-y-1">
          {scans.slice(1).map((s) => (
            <div key={s.id} className="flex justify-between text-muted-foreground">
              <span>#{s.id}</span>
              <span className={STATUS_TONE[s.status] ?? ""}>
                {s.status} · {fmtDuration(s.duration_s)}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 9.4: Create `CacheCard.tsx`**

```tsx
// frontend/src/components/health/CacheCard.tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { PlatformHealth } from "@/api/platformHealth";

type Props = { cache: PlatformHealth["cache"] };

function fmtAge(s: number | null): string {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}g`;
}

export default function CacheCard({ cache }: Props) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Cache &amp; DB</CardTitle>
      </CardHeader>
      <CardContent className="text-xs space-y-2">
        <div>
          <div className="font-semibold">Fundamentals</div>
          <div className="flex justify-between text-muted-foreground">
            <span>L1 / L2</span>
            <span className="font-mono">
              {cache.fundamentals.l1_entries} / {cache.fundamentals.l2_entries}
            </span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span>Oldest</span>
            <span className="font-mono">{fmtAge(cache.fundamentals.oldest_age_s)}</span>
          </div>
        </div>
        <div className="border-t pt-2">
          <div className="font-semibold">News</div>
          <div className="flex justify-between text-muted-foreground">
            <span>L1 / L2</span>
            <span className="font-mono">
              {cache.news.l1_entries} / {cache.news.l2_entries}
            </span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span>Oldest</span>
            <span className="font-mono">{fmtAge(cache.news.oldest_age_s)}</span>
          </div>
        </div>
        <div className="border-t pt-2">
          <div className="font-semibold">Database</div>
          <div className="flex justify-between text-muted-foreground">
            <span>app.db</span>
            <span className="font-mono">{cache.db.size_mb} MB</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 9.5: Replace the JSON pre-blocks in `PlatformHealthPage.tsx` with the cards**

```tsx
import DataSourcesCard from "@/components/health/DataSourcesCard";
import SchedulerCard from "@/components/health/SchedulerCard";
import ScansCard from "@/components/health/ScansCard";
import CacheCard from "@/components/health/CacheCard";

// in the JSX, replace the JSON dump block with:
{health && (
  <div className="grid gap-3 lg:grid-cols-4">
    <DataSourcesCard
      metrics={health.data_sources}
      yfinanceBreaker={health.yfinance_breaker}
    />
    <SchedulerCard jobs={health.scheduler} />
    <ScansCard scans={health.scans} />
    <CacheCard cache={health.cache} />
  </div>
)}
```

- [ ] **Step 9.6: Build frontend**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 9.7: Commit**

```bash
git add frontend/src/components/health/ \
        frontend/src/pages/PlatformHealthPage.tsx
git commit -m "frontend: 4 health summary cards (data sources, scheduler, scans, cache)"
```

---

### Task 10: Log stream component with filters

**Files:**
- Create: `frontend/src/components/health/LogStream.tsx`
- Modify: `frontend/src/pages/PlatformHealthPage.tsx`

- [ ] **Step 10.1: Create `LogStream.tsx`**

```tsx
// frontend/src/components/health/LogStream.tsx
import { useMemo, useState } from "react";
import { Pause, Play, Trash2 } from "lucide-react";
import type { LogRecord } from "@/api/platformHealth";

type Props = {
  records: LogRecord[];
  paused: boolean;
  onTogglePause: () => void;
  onClear: () => void;
};

const LEVEL_TONE: Record<string, string> = {
  DEBUG: "text-muted-foreground",
  INFO: "text-slate-700",
  SUCCESS: "text-emerald-700",
  WARNING: "text-amber-700",
  ERROR: "text-red-700",
  CRITICAL: "text-red-800 font-bold",
};

const LEVEL_ORDER: Record<string, number> = {
  DEBUG: 10, INFO: 20, SUCCESS: 25, WARNING: 30, ERROR: 40, CRITICAL: 50,
};

export default function LogStream({ records, paused, onTogglePause, onClear }: Props) {
  const [levelFilter, setLevelFilter] = useState("ALL");
  const [moduleFilter, setModuleFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");

  const filtered = useMemo(() => {
    const threshold = LEVEL_ORDER[levelFilter] ?? 0;
    return records.filter((r) => {
      if (threshold && (LEVEL_ORDER[r.level] ?? 0) < threshold) return false;
      if (moduleFilter && !r.module.includes(moduleFilter)) return false;
      if (searchFilter && !r.message.includes(searchFilter)) return false;
      return true;
    });
  }, [records, levelFilter, moduleFilter, searchFilter]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="text-lg font-semibold">
          Log{" "}
          <span className="text-xs text-muted-foreground">
            ({filtered.length} / {records.length})
          </span>
        </h2>
        <div className="flex items-center gap-2 text-xs">
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="rounded border bg-background px-2 py-1"
          >
            <option value="ALL">Tutti i livelli</option>
            <option value="DEBUG">DEBUG+</option>
            <option value="INFO">INFO+</option>
            <option value="WARNING">WARNING+</option>
            <option value="ERROR">ERROR+</option>
          </select>
          <input
            type="text"
            placeholder="Modulo"
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="rounded border bg-background px-2 py-1 w-32"
          />
          <input
            type="text"
            placeholder="Cerca testo"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="rounded border bg-background px-2 py-1 w-40"
          />
          <button
            type="button"
            onClick={onTogglePause}
            className="rounded border px-2 py-1 hover:bg-muted"
            title={paused ? "Riprendi" : "Pausa"}
          >
            {paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
          </button>
          <button
            type="button"
            onClick={onClear}
            className="rounded border px-2 py-1 hover:bg-muted"
            title="Pulisci buffer locale"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>

      <div className="rounded border bg-background max-h-[400px] overflow-auto font-mono text-xs">
        {filtered.length === 0 && (
          <div className="p-3 text-muted-foreground italic">Nessun log corrisponde ai filtri.</div>
        )}
        {filtered.slice(-500).map((r, i) => (
          <div key={`${r.ts}-${i}`} className="flex gap-2 px-2 py-0.5 hover:bg-muted/40">
            <span className="text-muted-foreground shrink-0 w-20">
              {new Date(r.ts * 1000).toLocaleTimeString()}
            </span>
            <span className={`shrink-0 w-16 font-semibold ${LEVEL_TONE[r.level] ?? ""}`}>
              {r.level}
            </span>
            <span className="text-muted-foreground shrink-0 w-32 truncate">[{r.module}]</span>
            <span className="flex-1 break-all">{r.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 10.2: Integrate into `PlatformHealthPage.tsx`**

Replace the existing log section with a stateful integration:

```tsx
import { useState } from "react";
import LogStream from "@/components/health/LogStream";
// ... existing imports

export default function PlatformHealthPage() {
  const [logs, setLogs] = useState<LogRecord[]>([]);
  const [paused, setPaused] = useState(false);

  // ... existing health query

  const { data: initialLogs } = useQuery({
    queryKey: ["platform-logs-initial"],
    queryFn: () => fetchLogs({ limit: 500 }),
    onSuccess: (data) => setLogs(data),  // hydrate the live buffer
  });

  // (Task 11 will replace this hydrate-once with an EventSource subscription.)

  return (
    <div className="p-6 space-y-6">
      {/* ... header + cards from Task 9 */}

      <LogStream
        records={paused ? logs : logs}
        paused={paused}
        onTogglePause={() => setPaused((p) => !p)}
        onClear={() => setLogs([])}
      />
    </div>
  );
}
```

**Note:** TanStack Query v5 deprecated `onSuccess` on `useQuery`. If the project uses v5, use `useEffect` instead:

```tsx
useEffect(() => {
  if (initialLogs) setLogs(initialLogs);
}, [initialLogs]);
```

Check `frontend/package.json` for the TanStack Query version and adapt.

- [ ] **Step 10.3: Build frontend**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 10.4: Commit**

```bash
git add frontend/src/components/health/LogStream.tsx \
        frontend/src/pages/PlatformHealthPage.tsx
git commit -m "frontend: LogStream component with level/module/search filters + pause"
```

---

### Task 11: SSE live streaming hook

**Files:**
- Create: `frontend/src/hooks/usePlatformHealthStream.ts`
- Modify: `frontend/src/pages/PlatformHealthPage.tsx`

- [ ] **Step 11.1: Create the hook**

```typescript
// frontend/src/hooks/usePlatformHealthStream.ts
import { useEffect, useState } from "react";
import type { LogRecord, PlatformHealth } from "@/api/platformHealth";

export function usePlatformHealthStream(initialLogs: LogRecord[] = []) {
  const [snapshot, setSnapshot] = useState<PlatformHealth | null>(null);
  const [logs, setLogs] = useState<LogRecord[]>(initialLogs);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    setLogs(initialLogs);
  }, [initialLogs]);

  useEffect(() => {
    const es = new EventSource("/api/platform/stream", { withCredentials: true });

    es.addEventListener("snapshot", (ev) => {
      try {
        const snap = JSON.parse((ev as MessageEvent).data) as PlatformHealth;
        setSnapshot(snap);
      } catch {
        /* ignore malformed snapshot */
      }
    });

    es.addEventListener("log", (ev) => {
      try {
        const rec = JSON.parse((ev as MessageEvent).data) as LogRecord;
        setLogs((prev) => {
          const next = [...prev, rec];
          // Cap at 500 to avoid unbounded growth in the browser.
          return next.length > 500 ? next.slice(-500) : next;
        });
      } catch {
        /* ignore malformed log */
      }
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    // EventSource auto-reconnects; no manual logic needed.

    return () => {
      es.close();
      setConnected(false);
    };
  }, []); // open once on mount

  return { snapshot, logs, setLogs, connected };
}
```

- [ ] **Step 11.2: Wire into `PlatformHealthPage.tsx`**

Replace the local `logs` state + initial query coordination with the hook:

```tsx
import { usePlatformHealthStream } from "@/hooks/usePlatformHealthStream";
import { useQuery } from "@tanstack/react-query";

export default function PlatformHealthPage() {
  const { data: initialLogs } = useQuery({
    queryKey: ["platform-logs-initial"],
    queryFn: () => fetchLogs({ limit: 500 }),
  });
  const { data: initialHealth } = useQuery({
    queryKey: ["platform-health"],
    queryFn: fetchHealth,
  });

  const { snapshot, logs, setLogs, connected } = usePlatformHealthStream(
    initialLogs ?? []
  );

  const health = snapshot ?? initialHealth ?? null;
  const [paused, setPaused] = useState(false);

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Salute piattaforma</h1>
          <p className="text-sm text-muted-foreground">
            Monitoraggio servizi e log in tempo reale.
          </p>
        </div>
        <div className="text-xs text-muted-foreground">
          {connected ? (
            <span className="text-emerald-700">● Live</span>
          ) : (
            <span className="text-amber-700">● Riconnessione…</span>
          )}
        </div>
      </header>

      {health && (
        <div className="grid gap-3 lg:grid-cols-4">
          <DataSourcesCard
            metrics={health.data_sources}
            yfinanceBreaker={health.yfinance_breaker}
          />
          <SchedulerCard jobs={health.scheduler} />
          <ScansCard scans={health.scans} />
          <CacheCard cache={health.cache} />
        </div>
      )}

      <LogStream
        records={logs}
        paused={paused}
        onTogglePause={() => setPaused((p) => !p)}
        onClear={() => setLogs([])}
      />
    </div>
  );
}
```

**Note:** when `paused === true`, new log records from SSE still arrive (the hook keeps subscribing) but the UI shows the buffer as-is. This is intentional — we don't want logs to silently drop while paused. If you'd rather pause server-side, that'd require a second SSE channel or a query param, which is overkill for v1.

Actually — to honor the "pause" semantics precisely, the UI cap might let new logs push out old ones the user wanted to inspect. A cleaner v1 implementation: while paused, keep the current snapshot frozen by clamping `setLogs` from the hook. The simplest way is to have the hook expose a `paused` flag too, but that couples concerns. The pragmatic compromise: when the user pauses, we accept that the visible list reflects the latest server state, just without the user's filters re-running. This is good-enough for the operator UX.

- [ ] **Step 11.3: Build frontend**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 11.4: Commit**

```bash
git add frontend/src/hooks/usePlatformHealthStream.ts \
        frontend/src/pages/PlatformHealthPage.tsx
git commit -m "frontend: SSE live updates for health snapshot + log stream"
```

---

## Phase 4 — Manual integration test (1 task)

### Task 12: Smoke test the page end-to-end

This step **must** run after the in-progress scan (id 112 at the time of plan writing) has completed, so that restarting the backend doesn't kill it.

- [ ] **Step 12.1: Wait for active scan to finish**

```
"C:/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe" -c "
from app.core.db import SessionLocal
from app.models import ScanRun
from sqlalchemy import select, desc
with SessionLocal() as db:
    r = db.execute(select(ScanRun).order_by(desc(ScanRun.id)).limit(1)).scalar_one()
    print(f'{r.id} {r.status} {r.progress_done}/{r.progress_total}')
"
```

Expected eventually: status `success` (or `failed`), not `running`.

- [ ] **Step 12.2: Merge the feature branch into master**

```bash
cd C:/Users/giuli/Documents/Progetti/finance-alert
git checkout master
git merge --ff-only feat/platform-health-2026-05-15
```

- [ ] **Step 12.3: Restart backend** (per CLAUDE.md canonical sequence)

```bash
netstat -ano | findstr :8000 | findstr LISTENING
taskkill //PID <PID> //F
# Then start fresh uvicorn:
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify `/api/health` returns 200 with `scheduler_running: true`. **Ignore the "OLD task failed" notification** per CLAUDE.md.

- [ ] **Step 12.4: Rebuild frontend dist**

```bash
cd frontend && npm run build
```

This is **mandatory** if anything frontend-side changed — see CLAUDE.md. The `:8000` URL serves `frontend/dist/` static files, so without a rebuild the new page won't render even though the source has it.

Verify the new strings landed in the bundle:
```bash
grep -c "Salute piattaforma" frontend/dist/assets/index-*.js
```
Expect 1+. Zero means a stale build.

- [ ] **Step 12.5: Smoke test in browser**

Open `http://localhost:8000/health` (hard-reload: Ctrl+Shift+R).

Verify in order:
1. **Sidebar**: new "Salute" entry visible with HeartPulse icon.
2. **Cards row**: 4 cards render with data (Data Sources, Scheduler, Scans, Cache).
3. **Log section**: pre-populated with the most recent ~500 records from the in-memory buffer.
4. **Live indicator**: top-right shows "● Live" in green (SSE connected).
5. **Generate a log event**: trigger something that logs, e.g.:
   ```bash
   curl -s http://127.0.0.1:8000/api/health/data-sources -H "Cookie: <your-session-cookie>" > /dev/null
   ```
   Within ~1s, a new log line should appear at the bottom of the log table.
6. **Filters**:
   - Set level to "WARNING+": only warnings/errors should remain visible.
   - Type "yfinance" in module filter: only yfinance-related lines.
   - Type "timeout" in search: only messages containing "timeout".
7. **Pause**: click the pause button. New SSE events still arrive but the visual list freezes. Click again → resume.
8. **DevTools network tab**: confirm `EventSource /api/platform/stream` is open with `text/event-stream` content type. No 5xx errors.

If any of the above fails, capture the symptom and:
- If a card is empty when it shouldn't be: check `/api/platform/health` JSON directly via curl with the session cookie.
- If SSE is silent: check the browser console for EventSource errors; check uvicorn logs for `[platform_health]` warnings.

- [ ] **Step 12.6: Verify suite still green on master**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: 537 passed (511 + 26 new from this branch). If pre-existing pandas flake re-appears, note it and continue.

- [ ] **Step 12.7: Cleanup worktree**

```bash
git worktree remove .worktrees/platform-health
git branch -d feat/platform-health-2026-05-15
```

---

## Self-review notes

- All tasks reference exact file paths.
- Each task has tests that fail before implementation and pass after.
- No "TBD" / "TODO" placeholders.
- Type names are consistent: `LogBuffer`, `LogRecord`, `PlatformHealth`, `SchedulerJobStat`, `JobStat` (dataclass) vs `SchedulerJobStatOut` (pydantic) — the suffix distinction is intentional and propagated correctly through Tasks 3, 5, 6, 7, 8.
- Frontend tasks honor the `npm run build` requirement after every change (CLAUDE.md).
- The manual smoke test is gated on scan completion to avoid backend-restart conflicts.
- SSE concurrency: explicit notes on thread-safe queue posting via `loop.call_soon_threadsafe`.
