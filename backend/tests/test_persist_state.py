"""Operational state survives a kill+restart: data-source health counters,
scheduler job stats, and the yfinance breaker. The Salute page (outage status,
last-error hints, job history, breaker) is no longer blanked on restart."""
from datetime import UTC, datetime, timedelta

from app.core import persist_json


def test_persist_json_roundtrip(tmp_path):
    p = tmp_path / "x.json"
    assert persist_json.read_json(p) is None          # missing -> None
    persist_json.write_json(p, {"a": {"n": 1}})
    assert persist_json.read_json(p) == {"a": {"n": 1}}


def test_persist_json_concurrent_writers_no_enoent(tmp_path):
    """Many threads writing the SAME path at once must not warn nor corrupt.

    Regression: a fixed '<name>.tmp' raced — one thread renamed the shared tmp
    into place, another hit ENOENT on replace and logged '[persist_json] failed
    to write … No such file or directory' (the recurring Salute-page warning
    under APScheduler's thread pool). write_json SWALLOWS the OSError, so the
    symptom is the LOG, not an exception — capture it. Unique per-call tmp
    (mkstemp) fixes it: last write wins, file stays valid, no orphan tmp.
    """
    import threading

    from loguru import logger

    captured: list[str] = []
    sink = logger.add(lambda m: captured.append(str(m)), level="WARNING")
    try:
        p = tmp_path / "scheduler_metrics.json"

        def writer(n: int) -> None:
            for i in range(60):
                persist_json.write_json(p, {"w": n, "i": i})

        threads = [threading.Thread(target=writer, args=(k,)) for k in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        logger.remove(sink)

    failed = [c for c in captured if "failed to write" in c]
    assert failed == [], f"persist_json warned under concurrency: {failed[:2]}"
    assert isinstance(persist_json.read_json(p), dict)          # never corrupt
    assert list(tmp_path.glob("*.tmp")) == []                   # no orphan tmp


def test_data_source_metrics_roundtrip():
    from app.services import data_source_metrics as m
    m.reset()
    m.record_success("yfinance", "ohlcv", count=3)
    m.record_failure("finnhub", "news", reason="HTTP 403")
    data = m._serialize_locked()                       # pure snapshot
    m.reset()
    assert m.snapshot() == []
    m.hydrate_from_dict(data)
    by = {(s.source, s.op): s for s in m.snapshot()}
    assert by[("yfinance", "ohlcv")].success == 3
    assert by[("finnhub", "news")].failure == 1
    assert by[("finnhub", "news")].last_failure_reason == "HTTP 403"
    m.reset()


def test_scheduler_metrics_roundtrip():
    from app.services.scheduler_metrics import JobStat, SchedulerMetrics
    a = SchedulerMetrics()
    a._stats["job1"] = JobStat(job_id="job1", last_result="ok", runs=5)
    a._stats["job2"] = JobStat(job_id="job2", last_result="error", errors=2, last_error="boom")
    data = a.to_dict()
    b = SchedulerMetrics()
    assert b.from_dict(data) == 2
    snap = {s.job_id: s for s in b.snapshot()}
    assert snap["job1"].runs == 5 and snap["job1"].last_result == "ok"
    assert snap["job2"].last_error == "boom" and snap["job2"].errors == 2


def test_yfinance_breaker_persists_on_trip(monkeypatch):
    from app.services import yfinance_health as yf
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)  # un-guard persistence
    saved: dict = {}
    monkeypatch.setattr(yf.breaker_state, "save", lambda k, until, **kw: saved.__setitem__(k, until))
    monkeypatch.setattr(yf.breaker_state, "clear", lambda k: saved.pop(k, None))
    yf.reset()
    for _ in range(yf.N_FAILURES):
        yf.record_failure("rate limit")
    assert "yfinance" in saved                          # blocked-until persisted on trip
    assert saved["yfinance"] > datetime.now(UTC)
    yf.record_success()                                 # close -> clears persisted state
    assert "yfinance" not in saved
    yf.reset()


def test_yfinance_breaker_restored_from_disk(monkeypatch):
    from app.services import yfinance_health as yf
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    future = datetime.now(UTC) + timedelta(minutes=4)
    monkeypatch.setattr(yf.breaker_state, "load", lambda k: future)
    yf.reset()
    assert yf.is_open() is False                        # clean slate
    assert yf.load_from_disk() is True
    assert yf.is_open() is True                          # restored open w/ remaining cooldown
    yf.reset()
