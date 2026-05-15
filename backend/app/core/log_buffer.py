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

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        with self._lock:
            self._subs.append(callback)

        def _unsub() -> None:
            with self._lock:
                try:
                    self._subs.remove(callback)
                except ValueError:
                    pass

        return _unsub


_INSTANCE = LogBuffer()
