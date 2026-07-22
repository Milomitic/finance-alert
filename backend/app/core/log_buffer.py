"""Ring buffer for log records with pub/sub.

Loguru writes here via a sink (see core/logging.py). SSE handlers
subscribe to receive each new record as it arrives.

Thread-safe: deque append is atomic, but we wrap subscriber notification
in a try/except per subscriber so one buggy listener can't break the rest
or break logging itself."""
import contextlib
import re
from collections import deque
from collections.abc import Callable
from datetime import datetime
from threading import Lock
from typing import Any

from loguru import logger

# Numeric severity for level-filtering. Mirror loguru's defaults.
_LEVEL_NO = {
    "TRACE": 5, "DEBUG": 10, "INFO": 20, "SUCCESS": 25,
    "WARNING": 30, "ERROR": 40, "CRITICAL": 50,
}

# Parser for loguru's DEFAULT file format
# (`TS | LEVEL | name:function:line - message`). Used to rehydrate the buffer
# from the on-disk log at startup — see `hydrate_from_lines` + core/logging.py.
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) \| "
    r"(?P<level>\w+)\s+\| "
    r"(?P<name>[\w.]+):(?P<function>[^:]*):(?P<line>\d+) - "
    r"(?P<message>.*)$"
)


def _parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse one default-format loguru file line into a buffer payload, or None
    for continuation/unparseable lines (e.g. multi-line exception tracebacks)."""
    m = _LOG_LINE_RE.match(line.rstrip("\n"))
    if m is None:
        return None
    try:
        ts = datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S.%f").timestamp()
    except ValueError:
        return None
    name = m["name"]
    return {
        "ts": ts,
        "level": m["level"],
        # Match the runtime sink's `module` (loguru's short module name) so the
        # UI source-filter behaves identically for live + rehydrated records.
        "module": name.rsplit(".", 1)[-1],
        "function": m["function"],
        "line": int(m["line"]),
        "message": m["message"],
        "exception": None,
    }


class LogBuffer:
    def __init__(self, maxlen: int = 2000) -> None:
        self._buf: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._subs: list[Callable[[dict[str, Any]], None]] = []
        self._lock = Lock()

    def append_record(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._buf.append(record)
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(record)
            except Exception as exc:  # noqa: BLE001
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

    def hydrate_from_lines(self, lines: list[str], max_records: int = 1000) -> int:
        """Pre-fill the buffer from on-disk log lines at startup so the live-log
        view (and its per-source filter) isn't empty after a restart — source
        errors from the previous run stay visible. Historical records are placed
        BEFORE any already-buffered runtime records to keep chronological order.
        Returns the number of records hydrated."""
        parsed = [rec for line in lines if (rec := _parse_log_line(line)) is not None]
        if not parsed:
            return 0
        parsed = parsed[-max_records:]
        with self._lock:
            existing = list(self._buf)
            self._buf.clear()
            for r in parsed:
                self._buf.append(r)
            for r in existing:
                self._buf.append(r)
        return len(parsed)

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        with self._lock:
            self._subs.append(callback)

        def _unsub() -> None:
            with self._lock, contextlib.suppress(ValueError):
                self._subs.remove(callback)

        return _unsub


_INSTANCE = LogBuffer()
