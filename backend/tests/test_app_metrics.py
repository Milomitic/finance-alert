"""`finance_alert_last_successful_run_timestamp_seconds` and its rehydration.

The four alert rules added on 2026-08-19 watch whether the app is ALIVE. This
metric is the one that says whether it is WORKING — a pod that stays up while
every scan fails keeps the other four silent.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.core import app_metrics
from app.models.scan_run import KIND_ALERTS_SCAN, KIND_SCORE_RECOMPUTE, ScanRun


def _value(kind: str) -> float:
    return app_metrics.LAST_SUCCESSFUL_RUN.labels(kind=kind)._value.get()


def _run(db, kind, status, completed_at, *, tz=True):
    db.add(ScanRun(
        kind=kind, trigger="cron", status=status,
        started_at=completed_at, completed_at=completed_at,
        progress_done=0, progress_total=0,
    ))
    db.commit()


class TestRecord:
    def test_stamps_the_gauge(self):
        when = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
        app_metrics.record_successful_run(KIND_ALERTS_SCAN, when)
        assert _value(KIND_ALERTS_SCAN) == pytest.approx(when.timestamp())

    def test_kinds_are_independent(self):
        a = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
        b = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
        app_metrics.record_successful_run(KIND_ALERTS_SCAN, a)
        app_metrics.record_successful_run(KIND_SCORE_RECOMPUTE, b)
        assert _value(KIND_ALERTS_SCAN) == pytest.approx(a.timestamp())
        assert _value(KIND_SCORE_RECOMPUTE) == pytest.approx(b.timestamp())

    def test_a_metrics_failure_never_propagates(self, monkeypatch):
        """This runs immediately after a scan that WORKED and committed. An
        exception here would turn a good run into a failed one over a gauge."""
        monkeypatch.setattr(
            app_metrics.LAST_SUCCESSFUL_RUN, "labels",
            lambda **_: (_ for _ in ()).throw(RuntimeError("registry exploded")),
        )
        app_metrics.record_successful_run(KIND_ALERTS_SCAN)  # must not raise


class TestHydration:
    """THE REASON THE HYDRATION EXISTS.

    A gauge lives in process memory and starts empty. Left that way, the
    metric would read "no successful scan" after every restart — including the
    OOM restart the alert on it exists to detect — so a real incident would
    immediately produce a SECOND, false alarm about scanning, then clear
    itself on the next cycle whether or not anything was wrong.
    """

    def test_restores_the_last_success_from_the_database(self, db):
        when = datetime.now(UTC) - timedelta(hours=3)
        _run(db, KIND_ALERTS_SCAN, "success", when)
        app_metrics.LAST_SUCCESSFUL_RUN.labels(kind=KIND_ALERTS_SCAN).set(0)

        app_metrics.hydrate_from_db(db)
        assert _value(KIND_ALERTS_SCAN) == pytest.approx(when.timestamp(), abs=1)

    def test_takes_the_most_recent_success_not_just_any(self, db):
        old = datetime.now(UTC) - timedelta(days=3)
        new = datetime.now(UTC) - timedelta(hours=2)
        _run(db, KIND_ALERTS_SCAN, "success", old)
        _run(db, KIND_ALERTS_SCAN, "success", new)

        app_metrics.hydrate_from_db(db)
        assert _value(KIND_ALERTS_SCAN) == pytest.approx(new.timestamp(), abs=1)

    def test_failed_runs_do_not_count(self, db):
        """A failed scan is precisely what this metric must keep reporting.
        Hydrating from it would erase the outage the alert is looking for."""
        good = datetime.now(UTC) - timedelta(days=2)
        bad = datetime.now(UTC) - timedelta(minutes=5)
        _run(db, KIND_ALERTS_SCAN, "success", good)
        _run(db, KIND_ALERTS_SCAN, "failed", bad)

        app_metrics.hydrate_from_db(db)
        assert _value(KIND_ALERTS_SCAN) == pytest.approx(good.timestamp(), abs=1)

    def test_naive_timestamps_are_read_as_utc(self, db):
        """SQLite returns naive datetimes, Postgres tz-aware ones. Reading a
        naive value as local time would shift the gauge by the host's UTC
        offset and make a fresh scan look hours stale — on this machine, two
        hours, which is most of the way to a 26h alert threshold being wrong."""
        naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        _run(db, KIND_ALERTS_SCAN, "success", naive)

        app_metrics.hydrate_from_db(db)
        expected = naive.replace(tzinfo=UTC).timestamp()
        assert _value(KIND_ALERTS_SCAN) == pytest.approx(expected, abs=1)

    def test_an_empty_database_leaves_the_gauge_alone(self, db):
        app_metrics.LAST_SUCCESSFUL_RUN.labels(kind=KIND_ALERTS_SCAN).set(123.0)
        app_metrics.hydrate_from_db(db)
        assert _value(KIND_ALERTS_SCAN) == 123.0

    def test_a_broken_query_does_not_stop_startup(self):
        class Exploding:
            def execute(self, *_a, **_k):
                raise RuntimeError("db is down")

        app_metrics.hydrate_from_db(Exploding())  # must not raise


class TestExposed:
    def test_the_series_reaches_the_metrics_endpoint(self):
        from prometheus_client import generate_latest

        app_metrics.record_successful_run(KIND_ALERTS_SCAN)
        body = generate_latest().decode()
        assert "finance_alert_last_successful_run_timestamp_seconds" in body
        assert f'kind="{KIND_ALERTS_SCAN}"' in body
