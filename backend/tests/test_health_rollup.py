"""Server-side health rollup (SAL-1): scheduler-jobs merge, overall verdict
rules, and the Telegram transition gating.

`compute_rollup` is pure over its inputs, so most tests feed
SimpleNamespace-shaped sources/scans instead of touching the DB. The
transition tests reset the module's in-memory notify state (persistence is
already a no-op under pytest) and monkeypatch the notifier seam.
"""
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services import health_rollup
from app.services.scheduler_metrics import SchedulerMetrics


def _src(role: str = "primary", health: str = "healthy", label: str = "Yahoo") -> SimpleNamespace:
    return SimpleNamespace(role=role, health=health, label=label)


def _scan(
    *,
    id: int = 1,
    status: str = "success",
    started_minutes_ago: float | None = 5,
    error_message: str | None = None,
) -> SimpleNamespace:
    started_at = (
        (datetime.now(UTC) - timedelta(minutes=started_minutes_ago)).isoformat()
        if started_minutes_ago is not None
        else None
    )
    return SimpleNamespace(
        id=id, status=status, started_at=started_at, error_message=error_message
    )


_CLOSED = {"state": "closed"}


def _rollup(**kw):
    defaults = dict(sources=[], breaker=_CLOSED, scheduler=[], scans=[])
    defaults.update(kw)
    return health_rollup.compute_rollup(**defaults)


# ─── compute_rollup: overall verdict rules ───────────────────────────────


def test_all_green_is_operational() -> None:
    overall, reasons = _rollup(
        sources=[_src("primary", "healthy"), _src("fallback", "idle")],
        scans=[_scan(status="success")],
        scheduler=[{"job_id": "scan_alerts", "last_result": "ok"}],
    )
    assert overall == "operational"
    assert reasons == []


def test_breaker_open_is_outage() -> None:
    overall, reasons = _rollup(breaker={"state": "open"})
    assert overall == "outage"
    assert any("Breaker yfinance" in r for r in reasons)


def test_failing_primary_is_outage() -> None:
    overall, reasons = _rollup(sources=[_src("primary", "failing", "Yahoo OHLCV")])
    assert overall == "outage"
    assert any("Yahoo OHLCV" in r for r in reasons)


def test_failing_fallback_is_degraded_not_outage() -> None:
    overall, _ = _rollup(sources=[_src("fallback", "failing", "Marketaux")])
    assert overall == "degraded"


def test_unavailable_source_never_degrades_the_banner() -> None:
    """Plan-gated 403 sources (finnhub upgrades, twelvedata) must NOT pin
    the banner amber forever — the SAL-1 audit finding."""
    overall, reasons = _rollup(
        sources=[
            _src("primary", "healthy"),
            _src("fallback", "unavailable", "Finnhub upgrades"),
        ],
    )
    assert overall == "operational"
    assert reasons == []


def test_stuck_running_scan_is_outage() -> None:
    overall, reasons = _rollup(
        scans=[_scan(status="running", started_minutes_ago=45)]
    )
    assert overall == "outage"
    assert any("possibile blocco" in r for r in reasons)


def test_stuck_scan_older_than_24h_still_outage() -> None:
    """Regression for the masked case: the frontend's old >24h guard hid a
    genuinely multi-day-stuck scan. The server rollup must NOT have it."""
    overall, _ = _rollup(
        scans=[_scan(status="running", started_minutes_ago=30 * 60)]  # 30h
    )
    assert overall == "outage"


def test_clock_skew_negative_elapsed_not_outage() -> None:
    overall, _ = _rollup(
        scans=[_scan(status="running", started_minutes_ago=-10)]
    )
    assert overall == "operational"


def test_recent_running_scan_not_stuck() -> None:
    overall, _ = _rollup(scans=[_scan(status="running", started_minutes_ago=10)])
    assert overall == "operational"


def test_scheduler_error_and_missed_are_degraded() -> None:
    for result in ("error", "missed"):
        overall, reasons = _rollup(
            scheduler=[{"job_id": "refresh_sec_13f", "last_result": result}]
        )
        assert overall == "degraded", result
        assert any("refresh_sec_13f" in r for r in reasons)


def test_last_scan_failed_is_degraded() -> None:
    overall, reasons = _rollup(
        scans=[_scan(status="failed", error_message="boom")]
    )
    assert overall == "degraded"
    assert any("Ultimo scan fallito" in r for r in reasons)


def test_user_cancelled_scan_not_degraded() -> None:
    """status='failed' with the cancel sentinel is a user action, not a
    platform problem."""
    overall, _ = _rollup(
        scans=[_scan(status="failed", error_message="Cancellato dall'utente")]
    )
    assert overall == "operational"


def test_older_failed_scan_behind_a_success_not_degraded() -> None:
    """Only the NEWEST scan's failure degrades — a later success supersedes."""
    overall, _ = _rollup(
        scans=[
            _scan(id=2, status="success"),
            _scan(id=1, status="failed", error_message="boom"),
        ]
    )
    assert overall == "operational"


def test_outage_reasons_include_degraded_ones_too() -> None:
    overall, reasons = _rollup(
        sources=[_src("primary", "failing", "Yahoo")],
        scheduler=[{"job_id": "kpi_rollup", "last_result": "error"}],
    )
    assert overall == "outage"
    # Outage reasons first, degraded appended — the operator sees everything.
    assert "Yahoo" in reasons[0]
    assert any("kpi_rollup" in r for r in reasons)


# ─── scheduler_jobs_payload: registered ⨝ stats merge ────────────────────


class _FakeJob:
    def __init__(self, id: str, next_run_time, trigger: str) -> None:
        self.id = id
        self.next_run_time = next_run_time
        self.trigger = trigger


def test_scheduler_jobs_payload_includes_never_run_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registered job with NO events yet must appear (runs=0) — before
    SAL-1 it was invisible until its first fire, so a dead cron looked
    identical to a healthy one."""
    import app.scheduler as scheduler_mod

    nrt = datetime.now(UTC) + timedelta(hours=2)
    fake_sched = SimpleNamespace(
        get_jobs=lambda: [
            _FakeJob("scan_alerts", nrt, "cron[hour='23', minute='30']"),
            _FakeJob("refresh_sec_13f", None, "cron[day_of_week='sat']"),
        ]
    )
    monkeypatch.setattr(scheduler_mod, "get_scheduler", lambda: fake_sched)

    metrics = SchedulerMetrics()
    metrics.on_event(SimpleNamespace(code=4096, job_id="scan_alerts", exception=None))
    import app.services.scheduler_metrics as sm_mod

    monkeypatch.setattr(sm_mod, "_INSTANCE", metrics)

    payload = {j["job_id"]: j for j in health_rollup.scheduler_jobs_payload()}
    # Ran job: stats joined with the registered metadata.
    assert payload["scan_alerts"]["runs"] == 1
    assert payload["scan_alerts"]["last_result"] == "ok"
    assert payload["scan_alerts"]["next_run_time"] == pytest.approx(nrt.timestamp())
    assert "cron" in payload["scan_alerts"]["trigger"]
    # Never-run job: present with zeroed stats.
    assert payload["refresh_sec_13f"]["runs"] == 0
    assert payload["refresh_sec_13f"]["last_result"] is None


def test_scheduler_jobs_payload_keeps_stats_only_leftovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A job with history but no longer registered (e.g. sweep disabled by
    config) stays visible instead of silently dropping."""
    import app.scheduler as scheduler_mod
    import app.services.scheduler_metrics as sm_mod

    monkeypatch.setattr(
        scheduler_mod, "get_scheduler", lambda: SimpleNamespace(get_jobs=lambda: [])
    )
    metrics = SchedulerMetrics()
    metrics.on_event(SimpleNamespace(code=4096, job_id="live_movers_sweep", exception=None))
    monkeypatch.setattr(sm_mod, "_INSTANCE", metrics)

    payload = {j["job_id"]: j for j in health_rollup.scheduler_jobs_payload()}
    assert payload["live_movers_sweep"]["runs"] == 1
    assert payload["live_movers_sweep"]["next_run_time"] is None
    assert payload["live_movers_sweep"]["trigger"] is None


def test_scheduler_jobs_payload_survives_scheduler_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/health must never 500 because scheduler introspection failed."""
    import app.scheduler as scheduler_mod

    def _boom():
        raise RuntimeError("scheduler down")

    monkeypatch.setattr(scheduler_mod, "get_scheduler", _boom)
    payload = health_rollup.scheduler_jobs_payload()
    assert isinstance(payload, list)


# ─── maybe_notify_transition: state-change + cooldown gating ─────────────


@pytest.fixture()
def notify_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """Clean transition state + captured notifier calls."""
    health_rollup.reset_notify_state()
    calls: list[tuple[str, list[str]]] = []

    from app.services import notifier_service

    def _capture(overall: str, reasons: list[str]) -> bool:
        calls.append((overall, reasons))
        return True

    monkeypatch.setattr(notifier_service, "notify_health_transition", _capture)
    monkeypatch.setattr(settings, "telegram_notify_health", True)
    yield calls
    health_rollup.reset_notify_state()


def test_notifies_on_transition_to_degraded(notify_calls) -> None:
    assert health_rollup.maybe_notify_transition("operational", []) is False
    assert health_rollup.maybe_notify_transition("degraded", ["motivo"]) is True
    assert notify_calls == [("degraded", ["motivo"])]


def test_same_state_repeat_reads_are_silent(notify_calls) -> None:
    health_rollup.maybe_notify_transition("degraded", ["a"])
    assert health_rollup.maybe_notify_transition("degraded", ["a"]) is False
    assert health_rollup.maybe_notify_transition("degraded", ["b"]) is False
    assert len(notify_calls) == 1


def test_escalation_degraded_to_outage_notifies_again(notify_calls) -> None:
    health_rollup.maybe_notify_transition("degraded", ["a"])
    assert health_rollup.maybe_notify_transition("outage", ["b"]) is True
    assert [c[0] for c in notify_calls] == ["degraded", "outage"]


def test_recovery_to_operational_is_silent(notify_calls) -> None:
    health_rollup.maybe_notify_transition("degraded", ["a"])
    assert health_rollup.maybe_notify_transition("operational", []) is False
    assert len(notify_calls) == 1


def test_cooldown_suppresses_flapping(notify_calls) -> None:
    """operational→degraded→operational→degraded within 6h notifies ONCE."""
    health_rollup.maybe_notify_transition("degraded", ["a"])
    health_rollup.maybe_notify_transition("operational", [])
    assert health_rollup.maybe_notify_transition("degraded", ["a"]) is False
    assert len(notify_calls) == 1


def test_cooldown_expiry_allows_renotification(notify_calls) -> None:
    health_rollup.maybe_notify_transition("degraded", ["a"])
    health_rollup.maybe_notify_transition("operational", [])
    # Backdate the last notification beyond the 6h window.
    with health_rollup._lock:
        health_rollup._state["last_notified"]["degraded"] = (
            time.time() - health_rollup.NOTIFY_COOLDOWN_SECONDS - 1
        )
    assert health_rollup.maybe_notify_transition("degraded", ["a"]) is True
    assert len(notify_calls) == 2


def test_flag_off_suppresses_but_tracks_state(
    notify_calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_notify_health", False)
    assert health_rollup.maybe_notify_transition("outage", ["a"]) is False
    assert notify_calls == []
    # State was tracked anyway: re-enabling doesn't re-fire on the same state.
    monkeypatch.setattr(settings, "telegram_notify_health", True)
    assert health_rollup.maybe_notify_transition("outage", ["a"]) is False


# ─── compute_rollup_from_db: convenience path for the probes job ─────────


def test_compute_rollup_from_db_smoke(db, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end over a real (empty) DB: no scans, catalog idle → operational.
    Scheduler is faked to avoid instantiating the real singleton."""
    import app.scheduler as scheduler_mod

    monkeypatch.setattr(
        scheduler_mod, "get_scheduler", lambda: SimpleNamespace(get_jobs=lambda: [])
    )
    from app.services import data_source_metrics

    data_source_metrics.reset()
    overall, reasons = health_rollup.compute_rollup_from_db(db)
    assert overall == "operational"
    assert reasons == []
