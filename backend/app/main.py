"""FastAPI application entry point."""
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import alerts as alerts_router
from app.api import auth as auth_router
from app.api import calendar as calendar_router
from app.api import catalog as catalog_router
from app.api import dashboard as dashboard_router
from app.api import institutionals as institutionals_router
from app.api import kpi as kpi_router
from app.api import market as market_router
from app.api import platform_health as platform_health_router
from app.api import market_detail as market_detail_router
from app.api import multi_tf as multi_tf_router
from app.api import price_alerts as price_alerts_router
from app.api import spotlight as spotlight_router
from app.api import rule_performance as rule_performance_router
from app.api import scan_log as scan_log_router
from app.api import scores as scores_router
from app.api import sectors as sectors_router
from app.api import stocks as stocks_router
from app.core.errors import UpstreamError
from app.core.logging import configure_logging, hydrate_log_buffer_from_disk
from app.scheduler import get_scheduler, start_scheduler, stop_scheduler

configure_logging()


def _cleanup_orphan_scans() -> None:
    """Mark any ScanRun still in 'running' state at startup as failed.

    Rationale: backend processes are uvicorn workers. If the previous instance
    crashed mid-scan (or was killed by `taskkill`), the row stays 'running'
    forever — the UI shows a phantom scan with a duration counter that grows
    indefinitely and the user can't trigger a new scan. Sweeping at startup
    closes the loop deterministically.

    Uses last_progress_at (or started_at as fallback) for the message so the
    user can tell how far the orphan got before dying.
    """
    from datetime import UTC, datetime

    from app.core.db import SessionLocal
    from app.models import ScanRun
    from app.scheduler.jobs.cleanup_orphan_scans_job import _STALE_AFTER_MINUTES
    from sqlalchemy import select

    with SessionLocal() as db:
        orphans = db.execute(
            select(ScanRun).where(ScanRun.status == "running")
        ).scalars().all()
        if not orphans:
            return
        now = datetime.now(UTC)
        closed_ids: list[int] = []
        kept_ids: list[int] = []
        for r in orphans:
            ref = r.last_progress_at or r.started_at
            if ref is not None and ref.tzinfo is None:
                ref = ref.replace(tzinfo=UTC)
            elapsed_min = int((now - ref).total_seconds() / 60) if ref else 999
            # Heartbeat-aware: a 'running' row with a RECENT heartbeat is
            # likely still alive in an EXTERNAL process (e.g. a scoped backfill
            # launched outside uvicorn). Restarting uvicorn must NOT false-fail
            # it — the row's heartbeat keeps advancing and the scan completes
            # and self-marks 'success'. Only close genuinely-stale rows here;
            # the periodic cleanup_orphan_scans_job catches any that go stale
            # later. (Same _STALE_AFTER_MINUTES threshold so the two agree.)
            if elapsed_min < _STALE_AFTER_MINUTES:
                kept_ids.append(r.id)
                continue
            r.status = "failed"
            r.phase = None
            r.error_message = (
                f"Backend riavviato durante lo scan (ultimo heartbeat ~{elapsed_min}min fa). "
                "Cleanup automatico all'avvio."
            )
            r.completed_at = now
            closed_ids.append(r.id)
        db.commit()
        if closed_ids:
            logger.warning(
                f"[startup] cleaned up {len(closed_ids)} orphan ScanRun row(s) "
                f"(ids={closed_ids})"
            )
        if kept_ids:
            logger.info(
                f"[startup] left {len(kept_ids)} ScanRun(s) running — recent "
                f"heartbeat, likely an external-process scan (ids={kept_ids})"
            )


def _hydrate_fetch_caches() -> None:
    """Restore L1 caches da L2. Logga timing + count di righe corrotte
    skippate, così una L2 sempre più sporca emerge nelle metriche."""
    import time as _time

    from app.services import stock_fundamentals_service, stock_news_service

    t0 = _time.perf_counter()
    try:
        n_fund_ok, n_fund_skip = stock_fundamentals_service.hydrate_l1_from_db()
        n_news_ok, n_news_skip = stock_news_service.hydrate_l1_from_db()
    except Exception as exc:  # noqa: BLE001 — boot-time best effort
        logger.warning(f"[startup] L1 hydration failed (non-fatal): {exc}")
        return

    elapsed_ms = (_time.perf_counter() - t0) * 1000
    if n_fund_ok or n_news_ok or n_fund_skip or n_news_skip:
        logger.info(
            f"[startup] L1 hydrated in {elapsed_ms:.0f}ms: "
            f"fundamentals={n_fund_ok} (skipped {n_fund_skip}), "
            f"news={n_news_ok} (skipped {n_news_skip})"
        )



def _warm_premarket_on_boot() -> None:
    """Pre-market cache lives in-process, so a backend restart blanks it
    → the pre-market card vanishes (its only refresh button is INSIDE
    the card, so the user has no manual recourse) until the 5-min
    scheduler tick. Kick one refresh at boot, in a daemon thread so
    startup isn't blocked. Reuses the scheduler job verbatim — it
    self-gates to the US pre-market window and no-ops cheaply
    otherwise, so this is safe to call unconditionally on every boot."""
    try:
        from app.scheduler.jobs.refresh_premarket import (
            run_refresh_premarket,
        )
        threading.Thread(
            target=run_refresh_premarket,
            name="premarket-boot-warm",
            daemon=True,
        ).start()
    except Exception as exc:  # noqa: BLE001 — never block startup
        logger.warning(f"[startup] premarket warm skipped: {exc}")


def _catch_up_scan_on_boot() -> None:
    """Local-first timeliness fix. The in-process scan cron only fires while
    the backend is running, so on a desktop machine that's off overnight the
    nightly scan is silently missed and signals surface days late (only on the
    user's next manual scan — the "rilevato in ritardo" complaint). On boot,
    if the last SUCCESSFUL scan is older than settings.scan_startup_stale_hours,
    kick a full scan in a daemon thread so opening the app detects the signals
    from the days the machine was off — without blocking startup."""
    import os
    from datetime import UTC, datetime, timedelta

    from app.core.config import settings

    # Never kick a real universe scan from a test's TestClient lifespan.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    stale_hours = settings.scan_startup_stale_hours
    if stale_hours <= 0:
        return
    try:
        from sqlalchemy import desc, select

        from app.core.db import SessionLocal
        from app.models import ScanRun

        with SessionLocal() as db:
            last = db.execute(
                select(ScanRun)
                .where(ScanRun.status == "success")
                .order_by(desc(ScanRun.completed_at))
                .limit(1)
            ).scalars().first()
        fresh = False
        if last is not None and last.completed_at is not None:
            done = last.completed_at
            if done.tzinfo is None:
                done = done.replace(tzinfo=UTC)
            fresh = (datetime.now(UTC) - done) < timedelta(hours=stale_hours)
        if fresh:
            logger.info("[startup] last scan is fresh — skipping catch-up")
            return

        # Don't pile a catch-up on top of a scan the user already kicked: two
        # concurrent scans both run fetch_and_upsert and deadlock SQLite
        # ('database is locked'). run_scan_alerts also guards via the slot, but
        # skipping here avoids even spawning a thread that would immediately bail.
        from app.services import scan_lock

        if scan_lock.is_running():
            logger.info("[startup] a scan is already running — skipping catch-up")
            return

        from app.scheduler.jobs.scan_alerts import run_scan_alerts
        logger.info("[startup] last scan stale/absent — kicking catch-up scan")
        threading.Thread(
            target=run_scan_alerts,
            name="scan-boot-catchup",
            daemon=True,
        ).start()
    except Exception as exc:  # noqa: BLE001 — never block startup
        logger.warning(f"[startup] catch-up scan skipped: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _cleanup_orphan_scans()
    _hydrate_fetch_caches()
    # Pre-fill the live-log ring buffer from the on-disk log tail so the
    # Salute log view (and its per-source filter) survives restarts.
    hydrate_log_buffer_from_disk()
    # Restore operational state so a kill+restart doesn't blank the Salute page:
    # data-source health/outage counters, scheduler job history, and the yfinance
    # breaker (the 4 fallback breakers already persist via breakers.json).
    from app.services import data_source_metrics, scheduler_metrics, yfinance_health
    data_source_metrics.load_from_disk()
    scheduler_metrics._INSTANCE.load_from_disk()
    yfinance_health.load_from_disk()
    start_scheduler()
    _warm_premarket_on_boot()
    _catch_up_scan_on_boot()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="Finance Alert", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    dur_ms = (time.perf_counter() - start) * 1000
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({dur_ms:.1f}ms)")
    return response


app.include_router(auth_router.router)
app.include_router(stocks_router.router)
app.include_router(catalog_router.router)
app.include_router(rule_performance_router.router)
app.include_router(scan_log_router.router)
app.include_router(alerts_router.router)
app.include_router(dashboard_router.router)
app.include_router(market_router.router)
app.include_router(market_detail_router.router)
app.include_router(multi_tf_router.router)
app.include_router(price_alerts_router.router)
app.include_router(spotlight_router.router)
app.include_router(scores_router.router)
app.include_router(sectors_router.router)
app.include_router(calendar_router.router)
app.include_router(institutionals_router.router)
app.include_router(platform_health_router.router)
app.include_router(kpi_router.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "scheduler_running": get_scheduler().running, "version": app.version}


@app.post("/api/admin/warmup-fundamentals")
def warmup_fundamentals(
    limit: int | None = None,
    skip_cached: bool = True,
) -> dict[str, object]:
    """Iterate the catalog (largest market_cap first) and prefetch fundamentals
    in-process. Honors the yfinance circuit breaker — when it opens we abort
    cleanly instead of wasting requests on a blocked endpoint.

    `limit`: cap how many tickers to process (None = all).
    `skip_cached`: don't hit network for tickers whose cache is still fresh.

    Runs synchronously (blocks the request). For ~1100 stocks at ~0.4s each
    this is ~7-8min on a warm Yahoo, instant when the breaker is open.
    """
    import time
    from app.core.db import SessionLocal
    from app.models import Stock
    from app.services import yfinance_health
    from app.services.stock_fundamentals_service import (
        _CACHE, _TTL_SECONDS, get_fundamentals,
    )
    from sqlalchemy import select

    db = SessionLocal()
    try:
        stocks = db.execute(
            select(Stock).order_by(Stock.market_cap.desc().nullslast())
        ).scalars().all()
        if limit:
            stocks = stocks[:limit]
        ok = err = empty = cached_skip = 0
        breaker_aborted_at: int | None = None
        now = time.time()
        for i, s in enumerate(stocks):
            if yfinance_health.is_open():
                breaker_aborted_at = i
                break
            if skip_cached:
                c = _CACHE.get(s.ticker)
                if c is not None and (now - c.fetched_at) < _TTL_SECONDS:
                    cached_skip += 1
                    continue
            try:
                f = get_fundamentals(s.ticker)
                if f.error:
                    err += 1
                elif f.annual or (f.micro and f.micro.trailing_pe is not None):
                    ok += 1
                else:
                    empty += 1
            except UpstreamError as e:
                logger.warning(
                    f"[warmup] upstream {e.source}.{e.op} failed for {s.ticker}: {e}"
                )
                err += 1
            except Exception:  # noqa: BLE001 — defensive last-resort
                err += 1
            time.sleep(0.3)
        # Now that the fundamentals cache is warm, recompute scores so the
        # values reflect the freshly-fetched data. Non-fatal — warmup itself
        # has already reported its own success/failure counts.
        scores_recomputed = 0
        try:
            from app.services import score_service
            scores_recomputed, scores_failed = score_service.recompute_all(db)
            logger.info(
                f"[warmup] recomputed {scores_recomputed} stock scores "
                f"({scores_failed} failed)"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[warmup] score recompute failed (non-fatal): {exc}")
        return {
            "total_stocks": len(stocks),
            "succeeded": ok,
            "errors": err,
            "empty_payload": empty,
            "skipped_cached": cached_skip,
            "breaker_aborted_at": breaker_aborted_at,
            "yfinance_breaker": yfinance_health.status(),
            "scores_recomputed": scores_recomputed,
        }
    finally:
        db.close()


@app.post("/api/admin/redownload-ohlcv")
def redownload_ohlcv(
    limit: int | None = None,
    period: str = "10y",
) -> dict[str, object]:
    """One-shot deep-backfill: wipe + re-fetch OHLCV for every stock at the
    requested yfinance period.

    Why this exists: the regular scan path uses `period="1mo"` for stocks
    whose latest bar is < 30 days old. So when the chart range was extended
    to 5Y, existing stocks (which already had 1Y of data) never qualified
    for the new 10Y deep-backfill — `needs_backfill` was always False.
    This endpoint forces the deep-backfill once across the catalog;
    afterwards, normal scans stay cheap.

    `limit`: cap how many stocks to process (None = all). Useful for
    smoke-testing the path on a small subset before committing to the
    full multi-minute run.
    `period`: yfinance period string. "10y" gives plenty of headroom for
    5Y views + long-window indicators; "max" pulls everything yfinance
    has but is slower. "5y" is the practical floor for the new chart range.

    Runs synchronously (blocks the request) — for ~1100 stocks at a
    chunk-of-100 cadence with yfinance batch fetch, expect ~3-5 minutes.
    """
    from app.core.db import SessionLocal
    from app.models import OhlcvDaily, Stock
    from app.services import yfinance_health
    from app.services.ohlcv_service import fetch_and_upsert
    from sqlalchemy import delete, select

    if period not in ("1y", "2y", "5y", "10y", "max"):
        raise HTTPException(
            status_code=422,
            detail="period must be one of 1y/2y/5y/10y/max",
        )

    db = SessionLocal()
    try:
        stocks = db.execute(
            select(Stock).order_by(Stock.market_cap.desc().nullslast())
        ).scalars().all()
        if limit:
            stocks = stocks[:limit]

        # Wipe existing OHLCV for the targeted stocks. The next fetch will
        # rebuild with the new period.
        stock_ids = [s.id for s in stocks]
        if stock_ids:
            db.execute(delete(OhlcvDaily).where(OhlcvDaily.stock_id.in_(stock_ids)))
            db.commit()

        # Re-fetch in chunks. Mirrors the scan-path chunk size + breaker check.
        chunk_size = 100
        ok = err = 0
        breaker_aborted_at: int | None = None
        for i in range(0, len(stocks), chunk_size):
            if yfinance_health.is_open():
                breaker_aborted_at = i
                break
            chunk = stocks[i : i + chunk_size]
            try:
                fetch_and_upsert(db, chunk, period=period)
                db.commit()
                ok += len(chunk)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[redownload-ohlcv] chunk failed: {exc}")
                db.rollback()
                err += len(chunk)
        return {
            "total_stocks": len(stocks),
            "succeeded": ok,
            "errors": err,
            "breaker_aborted_at": breaker_aborted_at,
            "period_used": period,
            "yfinance_breaker": yfinance_health.status(),
        }
    finally:
        db.close()


@app.get("/api/health/data-sources")
def data_sources_health() -> dict[str, object]:
    """Per-source per-operation success/failure counters + breaker state +
    gap-analysis suggestions. Useful to spot when a source needs a fallback."""
    from app.services import data_source_metrics, yfinance_health
    metrics = data_source_metrics.snapshot()
    return {
        "yfinance_breaker": yfinance_health.status(),
        "metrics": [
            {
                "source": m.source,
                "op": m.op,
                "success": m.success,
                "failure": m.failure,
                "success_rate": m.success_rate,
                "last_success_at": m.last_success_at,
                "last_failure_at": m.last_failure_at,
                "last_failure_reason": m.last_failure_reason,
                "health": m.health,
            }
            for m in metrics
        ],
        "suggestions": [
            {"op": g.op, "why": g.why, "suggestion": g.suggestion}
            for g in data_source_metrics.analyse_gaps()
        ],
    }


# Serve built frontend in prod-local mode if dist exists.
# Resolve relative to this file's location: backend/app/main.py -> ../../frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Serve hashed assets under /assets
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Serve top-level static files (favicon, etc.) and SPA fallback
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Anything under /api/ that wasn't matched by a real router is 404
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        # Try a literal file first (e.g. /vite.svg, /favicon.ico).
        # Defense-in-depth: resolve and verify the candidate stays inside FRONTEND_DIST
        # to prevent any path-traversal via crafted full_path values.
        if full_path:
            candidate = (FRONTEND_DIST / full_path).resolve()
            try:
                candidate.relative_to(FRONTEND_DIST)
            except ValueError:
                # Outside dist root — treat as not-found, fall through to SPA shell.
                candidate = None
            if candidate is not None and candidate.is_file():
                return FileResponse(candidate)

        # Otherwise serve the SPA shell
        index = FRONTEND_DIST / "index.html"
        return FileResponse(index)
    logger.info(f"Frontend dist served from {FRONTEND_DIST}")
else:
    logger.info(f"Frontend dist not built; SPA fallback disabled. (Expected at {FRONTEND_DIST})")
