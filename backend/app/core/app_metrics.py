"""Application-level Prometheus metrics.

WHY THIS EXISTS
---------------
The alert rules added on 2026-08-19 (infra/observability/app-alert-rules.yaml)
watch whether the app is ALIVE — memory, restarts, scrape reachability. None of
them can see whether it is WORKING. A pod that stays up while every scan fails
keeps all four silent, which is the more insidious outage: nothing crashes, the
dashboards look fine, and the data quietly stops moving.

Prometheus cannot answer that from the outside. The scan lines live in Loki and
alerting rules cannot query it, so the app has to say so itself. Hence one
gauge: the wall-clock time of the last run that actually finished.

THE PART THAT IS EASY TO GET WRONG
----------------------------------
A gauge lives in process memory and starts at nothing. Left like that, this
metric would read "no successful scan" for every restart — including the OOM
restart it exists to detect — so the first thing it would do after a real
incident is raise a SECOND, false alarm about scanning, and then resolve itself
on the next cycle whether or not anything was wrong.

So the value is REHYDRATED from `scan_runs` at startup. The database already
records every finished run; the gauge is a projection of it, not a new source
of truth. `hydrate_from_db` is what makes the metric survive the event it is
meant to report on.
"""
from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from prometheus_client import Gauge
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.scan_run import ScanRun

# Labelled by `kind` so the alert scan and the score recompute are covered by
# one metric and one rule instead of two of each. Values are the KIND_*
# constants on ScanRun ("alerts_scan", "score_recompute").
#
# NOTE: a labelled gauge emits NO series until `.labels(...)` is first set. On
# a brand-new database there is no successful run to hydrate from, so the
# series is genuinely absent rather than zero — which is why the alert rule
# pairs its staleness check with `absent()`.
LAST_SUCCESSFUL_RUN = Gauge(
    "finance_alert_last_successful_run_timestamp_seconds",
    "Unix timestamp of the last tracked background run that completed successfully.",
    ["kind"],
)


def record_successful_run(kind: str, when: datetime | None = None) -> None:
    """Stamp the gauge for `kind`. Never raises.

    Called from the runners' success path. A metrics problem must not fail a
    scan that actually worked, so every failure here degrades to a log line —
    the same rule the Telegram push next to it already follows.
    """
    try:
        ts = (when or datetime.now(UTC)).timestamp()
        LAST_SUCCESSFUL_RUN.labels(kind=kind).set(ts)
    except Exception as exc:  # noqa: BLE001 - never fail a good run over a metric
        logger.warning(f"[metrics] could not record successful {kind} run: {exc}")


def hydrate_from_db(db: Session) -> None:
    """Restore the gauge from `scan_runs` — see the module note.

    Reads MAX(completed_at) per kind over successful runs. Best-effort: if the
    query fails the app still starts, the series is simply missing until the
    next successful run stamps it.
    """
    try:
        rows = db.execute(
            select(ScanRun.kind, func.max(ScanRun.completed_at))
            .where(ScanRun.status == "success", ScanRun.completed_at.is_not(None))
            .group_by(ScanRun.kind)
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[metrics] scan-run hydration failed: {exc}")
        return

    for kind, completed_at in rows:
        if not kind or completed_at is None:
            continue
        # SQLite hands back naive datetimes; Postgres returns tz-aware ones.
        # Treating a naive value as local time would shift the gauge by the
        # host's UTC offset and make a fresh scan look hours stale.
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        LAST_SUCCESSFUL_RUN.labels(kind=kind).set(completed_at.timestamp())

    if rows:
        logger.info(f"[metrics] hydrated last-successful-run gauge for {len(rows)} kind(s)")

# ─── Cache occupancy ────────────────────────────────────────────────────────
# WHY. Profiling the app's memory from outside hits a wall: over one pod's
# life the working set climbs 543MB -> 806MB in eleven hours, in steps with
# long plateaus, and never returns to where it started. That shape has two
# very different explanations — caches warming up toward a legitimate ceiling,
# or something that never gets released — and `process_resident_memory_bytes`
# cannot tell them apart. The app holds ten in-process dict caches and
# exported nothing about any of them.
#
# These counts settle it: if entries plateau while RSS keeps climbing, it is a
# leak; if the two rise and level off together, the ~1GB baseline is simply
# the warm working set of a 999-stock universe and the OOM came from the scan
# spike landing on top of it.
#
# Counted at SCRAPE time via a collector rather than kept up to date by the
# caches themselves: no writer has to remember to maintain a counter, so the
# number cannot silently drift from the thing it describes. `len()` on a dict
# is O(1), and the collector is only asked once a minute.
_CACHE_SOURCES: list[tuple[str, str, str]] = [
    # (label, module, attribute)
    ("fundamentals", "app.services.stock_fundamentals_service", "_CACHE"),
    ("news", "app.services.stock_news_service", "_CACHE"),
    ("live_quote", "app.services.live_quote_service", "_CACHE"),
    ("live_sparkline", "app.services.live_sparkline_service", "_CACHE"),
    ("market_detail", "app.services.market_detail_service", "_CACHE"),
    ("timeframe", "app.services.timeframe_service", "_CACHE"),
    ("fx", "app.services.fx_service", "_CACHE"),
    ("nasdaq_analyst", "app.services.nasdaq_analyst_service", "_CACHE"),
]


class _CacheSizeCollector:
    """Reports how many entries each in-process cache holds, at scrape time."""

    def collect(self):  # noqa: D102 - prometheus_client protocol
        from importlib import import_module

        from prometheus_client.metrics_core import GaugeMetricFamily

        g = GaugeMetricFamily(
            "finance_alert_cache_entries",
            "Entries held in each in-process cache.",
            labels=["cache"],
        )
        for label, module_name, attr in _CACHE_SOURCES:
            try:
                cache = getattr(import_module(module_name), attr, None)
                if cache is None:
                    continue
                g.add_metric([label], float(len(cache)))
            except Exception:  # noqa: BLE001 - a scrape must never raise
                continue
        yield g


_cache_collector_registered = False


def register_cache_collector() -> None:
    """Register the cache-size collector once. Safe to call repeatedly.

    Idempotent because the default registry raises on a duplicate, and tests
    import this module more than once per session.
    """
    global _cache_collector_registered
    if _cache_collector_registered:
        return
    try:
        from prometheus_client import REGISTRY

        REGISTRY.register(_CacheSizeCollector())
        _cache_collector_registered = True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[metrics] cache collector not registered: {exc}")
