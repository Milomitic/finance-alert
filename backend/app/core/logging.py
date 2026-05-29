"""Loguru configuration: console + rotated file + in-memory buffer."""
import glob
import os
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


def hydrate_log_buffer_from_disk() -> None:
    """Pre-fill the ring buffer from the newest on-disk log file so the live-log
    view isn't empty right after a restart. Without this, the UI's per-source
    filter shows nothing until a fresh scan emits new lines — even though the
    source-failure WARNINGs (e.g. "[finnhub] HTTP 403") are right there in
    app.log. Read only the file's tail (~600KB) to keep startup cheap; the
    leading partial line just fails the regex and is skipped.

    Call this ONCE at real app startup (from the lifespan) — NOT from
    `configure_logging`, which tests invoke repeatedly (re-hydrating would
    re-import historical lines, including prior test markers)."""
    # Never pull production log history into the buffer during tests — the
    # TestClient lifespan would otherwise re-import old lines (incl. previous
    # test markers) into the shared singleton buffer and pollute assertions.
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    logs_dir = Path("./data/logs")
    try:
        files = sorted(glob.glob(str(logs_dir / "app*.log")), key=os.path.getmtime)
        if not files:
            return
        with open(files[-1], "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 600_000))
            tail = fh.read().decode("utf-8", errors="replace")
        n = log_buffer.hydrate_from_lines(tail.splitlines())
        logger.info(f"[logging] rehydrated {n} log records from {files[-1]}")
    except Exception as exc:  # noqa: BLE001 — hydration is best-effort
        logger.warning(f"[logging] buffer rehydration skipped: {exc}")
