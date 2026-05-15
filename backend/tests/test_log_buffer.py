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
    assert [r["message"] for r in seen] == ["a", "b"]


def test_subscribe_callback_exception_does_not_break_others():
    buf = LogBuffer(maxlen=10)
    good_seen: list[dict] = []

    def bad(_r):
        raise RuntimeError("subscriber crashed")

    buf.subscribe(bad)
    buf.subscribe(good_seen.append)
    buf.append_record({"ts": 0, "level": "INFO", "module": "m",
                       "function": "f", "line": 1, "message": "a"})
    assert len(good_seen) == 1
