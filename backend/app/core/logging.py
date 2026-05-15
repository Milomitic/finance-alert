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
