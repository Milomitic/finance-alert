"""Server-side health rollup for the Salute page + Telegram degradation push.

Three responsibilities (audit 2026-07-08 — the 13F crons died for months and
nothing on /health said so):

1. `scheduler_jobs_payload()` — merge the REGISTERED APScheduler jobs
   (job_id, next_run_time, trigger) with the per-job event stats from
   `scheduler_metrics`. Before this, a job was invisible on the Salute page
   until its FIRST event fired — a cron that never fires (dead scheduler,
   misconfigured trigger) was indistinguishable from a healthy one.

2. `compute_rollup(...)` — the overall 'operational' | 'degraded' | 'outage'
   verdict + human reasons[], computed SERVER-SIDE so every consumer (banner,
   SSE, Telegram) shares one truth. Same rules the frontend used to derive,
   with two deliberate changes:
     - NO >24h guard on the stuck-scan check (that guard masked a real
       multi-day stuck scan — only negative clock-skew is still excluded);
     - scheduler `last_result == "missed"` and a failed LAST scan count as
       degraded.
   Sources classified "unavailable" (all-403, plan-gated) are EXCLUDED from
   the degradation rules — a tier limitation is not an incident.

3. `maybe_notify_transition(...)` — best-effort Telegram push when the
   rollup TRANSITIONS to degraded/outage. The rollup is compute-on-read
   (stateless), so the last-notified state persists via the `persist_json`
   operational-state pattern (survives restarts → no re-notify storm on
   boot). Only fires on state CHANGE, max once per 6h per state, gated on
   `settings.telegram_notify_health`.
"""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from loguru import logger

from app.core import persist_json
from app.core.config import settings

# A running scan with no completion after this is considered stuck (same
# threshold the frontend derivation used).
STUCK_SCAN_MINUTES = 30
# Max one Telegram notification per state (degraded / outage) per window.
NOTIFY_COOLDOWN_SECONDS = 6 * 3600

# Persisted last-notified state — survives restarts so a reboot doesn't
# re-notify an ongoing degradation.
_STATE_FILE = persist_json.data_path("health_notify_state.json")

_lock = Lock()
# {"last_state": str|None, "last_notified": {state: epoch}} — hydrated lazily.
_state: dict[str, Any] = {"last_state": None, "last_notified": {}}
_state_loaded = False


# ─── scheduler truth ─────────────────────────────────────────────────


def scheduler_jobs_payload() -> list[dict]:
    """One dict per job: REGISTERED jobs first (with next_run_time +
    trigger repr), then any stats-only leftovers (e.g. a job disabled by
    config that still has persisted history). Each entry carries the
    scheduler_metrics stats joined by job_id, zeroed when the job has
    never fired an event."""
    from app.services.scheduler_metrics import _INSTANCE as scheduler_metrics

    stats = {s.job_id: s for s in scheduler_metrics.snapshot()}

    registered: list[tuple[str, float | None, str | None]] = []
    try:
        from app.scheduler import get_scheduler

        for job in get_scheduler().get_jobs():
            # Pending jobs (scheduler built but not started — e.g. under
            # tests) have no next_run_time slot yet → defensive getattr.
            nrt = getattr(job, "next_run_time", None)
            registered.append((
                job.id,
                nrt.timestamp() if nrt is not None else None,
                str(job.trigger),
            ))
    except Exception as exc:  # noqa: BLE001 — /health must never 500 on this
        logger.warning(f"[health_rollup] scheduler introspection failed: {exc!r}")

    out: list[dict] = []
    seen: set[str] = set()
    for job_id, next_run_time, trigger in registered:
        seen.add(job_id)
        s = stats.get(job_id)
        out.append({
            "job_id": job_id,
            "next_run_time": next_run_time,
            "trigger": trigger,
            "last_run_at": s.last_run_at if s else None,
            "last_result": s.last_result if s else None,
            "last_duration_ms": s.last_duration_ms if s else None,
            "last_error": s.last_error if s else None,
            "runs": s.runs if s else 0,
            "errors": s.errors if s else 0,
        })
    # Stats for job ids no longer registered (renamed job, disabled sweep):
    # keep them visible instead of silently dropping history.
    for job_id, s in stats.items():
        if job_id in seen:
            continue
        out.append({
            "job_id": job_id,
            "next_run_time": None,
            "trigger": None,
            "last_run_at": s.last_run_at,
            "last_result": s.last_result,
            "last_duration_ms": s.last_duration_ms,
            "last_error": s.last_error,
            "runs": s.runs,
            "errors": s.errors,
        })
    return out


# ─── rollup ──────────────────────────────────────────────────────────


def _scan_elapsed_minutes(started_at: Any) -> float | None:
    """Minutes since a scan started. Accepts a datetime (job path) or an
    ISO-8601 string (API payload path). None when unparseable."""
    if started_at is None:
        return None
    if isinstance(started_at, str):
        try:
            dt = datetime.fromisoformat(started_at)
        except ValueError:
            return None
    elif isinstance(started_at, datetime):
        dt = started_at
    else:
        return None
    # SQLite round-trips DateTime(timezone=True) as naive UTC — re-attach.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds() / 60.0


def compute_rollup(
    *,
    sources: list[Any],
    breaker: dict,
    scheduler: list[dict],
    scans: list[Any],
) -> tuple[str, list[str]]:
    """('operational'|'degraded'|'outage', reasons[]).

    `sources` are SourceWithUsage-shaped objects (attrs: role, health,
    label); `scans` are ScanRun rows or RecentScanOut models (attrs:
    id, status, started_at, error_message) NEWEST-FIRST."""
    outage: list[str] = []
    degraded: list[str] = []

    # Outage 1 — yfinance breaker open/half-open: the primary data path is
    # actively blocked.
    breaker_state = str(breaker.get("state") or "closed").lower()
    if breaker_state != "closed":
        outage.append(f"Breaker yfinance {breaker_state} — provider primario bloccato")

    # Outage 2 — a PRIMARY source failing. Fallback/scheduled failures are
    # reduced resilience, not a user-visible outage.
    for s in sources:
        if s.role == "primary" and s.health == "failing":
            outage.append(f"Fonte primaria in errore: {s.label}")
        elif s.role == "primary" and s.health == "degraded":
            degraded.append(f"Fonte primaria degradata: {s.label}")
        elif s.role != "primary" and s.health in ("failing", "degraded"):
            # NOTE: health == "unavailable" (plan-gated 403) deliberately
            # does NOT reach here — it must not pin the banner amber.
            degraded.append(f"Fonte {s.role} non operativa: {s.label}")

    # Outage 3 — a running scan stuck past the threshold. Only negative
    # elapsed (clock skew) is excluded; the old >24h guard is GONE — it
    # masked a genuinely multi-day-stuck scan (the audit trigger).
    for scan in scans:
        if getattr(scan, "status", None) != "running":
            continue
        elapsed_min = _scan_elapsed_minutes(getattr(scan, "started_at", None))
        if elapsed_min is not None and elapsed_min > STUCK_SCAN_MINUTES:
            outage.append(
                f"Scan #{scan.id} in esecuzione da {elapsed_min:.0f} min "
                f"(soglia {STUCK_SCAN_MINUTES} min) — possibile blocco"
            )

    # Degraded — scheduler jobs in error OR missed (a missed tick means the
    # scheduler is falling behind: exactly the silent-death mode this page
    # existed to catch and didn't).
    for j in scheduler:
        if j.get("last_result") == "error":
            degraded.append(f"Job scheduler in errore: {j.get('job_id')}")
        elif j.get("last_result") == "missed":
            degraded.append(f"Job scheduler mancato (missed): {j.get('job_id')}")

    # Degraded — the LAST scan failed (crash). A user-cancelled scan also
    # persists status='failed' but with the sentinel message — that's an
    # explicit user action, not a platform problem.
    if scans:
        last = scans[0]
        msg = getattr(last, "error_message", None) or ""
        if getattr(last, "status", None) == "failed" and not msg.startswith("Cancellato"):
            degraded.append(f"Ultimo scan fallito: {msg or 'errore sconosciuto'}")

    if outage:
        return "outage", outage + degraded
    if degraded:
        return "degraded", degraded
    return "operational", []


def compute_rollup_from_db(db) -> tuple[str, list[str]]:
    """Convenience for callers without a pre-built payload (the health-probes
    job): snapshots sources/breaker/scheduler in-process and reads the last
    10 scan rows."""
    from sqlalchemy import desc, select

    from app.models import ScanRun
    from app.services import source_catalog, yfinance_health

    scans = db.execute(
        select(ScanRun).order_by(desc(ScanRun.id)).limit(10)
    ).scalars().all()
    return compute_rollup(
        sources=source_catalog.full_snapshot(),
        breaker=yfinance_health.status(),
        scheduler=scheduler_jobs_payload(),
        scans=list(scans),
    )


# ─── transition notification ─────────────────────────────────────────


def _load_state_locked() -> None:
    """Hydrate `_state` from disk once. No disk under pytest (mirrors the
    scheduler_metrics pattern) — tests poke `_state` directly."""
    global _state_loaded
    if _state_loaded:
        return
    _state_loaded = True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    data = persist_json.read_json(_STATE_FILE)
    if data:
        _state["last_state"] = data.get("last_state")
        ln = data.get("last_notified")
        if isinstance(ln, dict):
            _state["last_notified"] = {
                k: float(v) for k, v in ln.items()
                if isinstance(v, (int, float))
            }


def _persist_state_locked() -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    persist_json.write_json(_STATE_FILE, {
        "last_state": _state["last_state"],
        "last_notified": _state["last_notified"],
    })


def maybe_notify_transition(overall: str, reasons: list[str]) -> bool:
    """Telegram push when the rollup TRANSITIONS into degraded/outage.

    Rules: only on state CHANGE (repeat reads of the same state are silent),
    only toward degraded/outage (recovery is silent — the daily digest is
    enough), max one notification per state per 6h (a source flapping
    between operational and degraded can't spam). Best-effort by contract:
    any error is swallowed after a warning log. Returns True when a
    notification was actually sent (test-friendly)."""
    try:
        with _lock:
            _load_state_locked()
            previous = _state["last_state"]
            changed = overall != previous
            _state["last_state"] = overall
            should_send = (
                changed
                and overall in ("degraded", "outage")
                and settings.telegram_notify_health
            )
            if should_send:
                last_ts = float(_state["last_notified"].get(overall) or 0.0)
                if time.time() - last_ts < NOTIFY_COOLDOWN_SECONDS:
                    should_send = False
                else:
                    _state["last_notified"][overall] = time.time()
            _persist_state_locked()
        if not should_send:
            return False
        from app.services import notifier_service

        return notifier_service.notify_health_transition(overall, reasons)
    except Exception as exc:  # noqa: BLE001 — never break a health read
        logger.warning(f"[health_rollup] transition notify failed: {exc!r}")
        return False


def reset_notify_state() -> None:
    """Clear the in-memory transition state — for tests."""
    global _state_loaded
    with _lock:
        _state["last_state"] = None
        _state["last_notified"] = {}
        _state_loaded = True
