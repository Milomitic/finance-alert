"""FastAPI application entry point."""
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
from app.api import market as market_router
from app.api import market_detail as market_detail_router
from app.api import multi_tf as multi_tf_router
from app.api import price_alerts as price_alerts_router
from app.api import spotlight as spotlight_router
from app.api import rule_catalog as rule_catalog_router
from app.api import rule_performance as rule_performance_router
from app.api import rule_preview as rule_preview_router
from app.api import rules as rules_router
from app.api import scores as scores_router
from app.api import sectors as sectors_router
from app.api import stocks as stocks_router
from app.api import watchlists as watchlists_router
from app.core.logging import configure_logging
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
    from sqlalchemy import select

    with SessionLocal() as db:
        orphans = db.execute(
            select(ScanRun).where(ScanRun.status == "running")
        ).scalars().all()
        if not orphans:
            return
        now = datetime.now(UTC)
        for r in orphans:
            ref = r.last_progress_at or r.started_at
            if ref is not None and ref.tzinfo is None:
                ref = ref.replace(tzinfo=UTC)
            elapsed_min = int((now - ref).total_seconds() / 60) if ref else 0
            r.status = "failed"
            r.phase = None
            r.error_message = (
                f"Backend riavviato durante lo scan (ultimo heartbeat ~{elapsed_min}min fa). "
                "Cleanup automatico all'avvio."
            )
            r.completed_at = now
        db.commit()
        logger.warning(
            f"[startup] cleaned up {len(orphans)} orphan ScanRun row(s) "
            f"(ids={[r.id for r in orphans]})"
        )


def _hydrate_fetch_caches() -> None:
    """Restore the in-memory L1 caches (fundamentals + news) from the
    persistent L2 fetch_cache table. Without this, the first request after
    every restart would round-trip the DB once per ticker; with it, L1 is
    warm before any client connects.

    Both calls are non-fatal — a corrupt L2 row should log + skip, not
    crash startup.
    """
    from app.services import stock_fundamentals_service, stock_news_service
    try:
        n_fund = stock_fundamentals_service.hydrate_l1_from_db()
        n_news = stock_news_service.hydrate_l1_from_db()
        if n_fund or n_news:
            logger.info(
                f"[startup] L1 hydrated: fundamentals={n_fund} news={n_news}"
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[startup] L1 hydration failed (non-fatal): {exc}")


def _ensure_default_rules() -> None:
    """Idempotent: create a global Rule row for every kind in the registry
    that doesn't already have one. The bootstrap script (`scripts/bootstrap_rules`)
    used to be the only call site, which meant new kinds added to the
    registry never reached the user until someone re-ran the script
    manually. Running on every backend boot fixes that — the call is a
    no-op when all kinds already exist, so the cost is one SELECT per
    registered kind on a process that just took ~2s to start up. */
    """
    try:
        from app.scripts.bootstrap_rules import ensure_global_rules
        ensure_global_rules()
    except Exception as exc:  # noqa: BLE001
        # Non-fatal — startup keeps going, just log.
        logger.warning(f"[startup] ensure_global_rules failed (non-fatal): {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _cleanup_orphan_scans()
    _hydrate_fetch_caches()
    _ensure_default_rules()
    start_scheduler()
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
app.include_router(watchlists_router.router)
app.include_router(catalog_router.router)
app.include_router(rules_router.router)
app.include_router(rule_catalog_router.router)
app.include_router(rule_performance_router.router)
app.include_router(rule_preview_router.router)
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
            except Exception:  # noqa: BLE001
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
