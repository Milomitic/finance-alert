"""Verify that loguru's logger.info/warning/error writes into the
in-memory ring buffer via the configured sink."""
from loguru import logger

from app.core.log_buffer import _INSTANCE as log_buffer
from app.core.logging import configure_logging


def test_logger_warning_lands_in_buffer():
    configure_logging()
    before = len(log_buffer.get_snapshot(limit=0))
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
