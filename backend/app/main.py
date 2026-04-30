"""FastAPI application entry point."""
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import auth as auth_router
from app.api import catalog as catalog_router
from app.api import stocks as stocks_router
from app.api import watchlists as watchlists_router
from app.core.logging import configure_logging
from app.scheduler import get_scheduler, start_scheduler, stop_scheduler

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
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


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "scheduler_running": get_scheduler().running, "version": app.version}


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

        # Try a literal file first (e.g. /vite.svg, /favicon.ico)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)

        # Otherwise serve the SPA shell
        index = FRONTEND_DIST / "index.html"
        return FileResponse(index)
    logger.info(f"Frontend dist served from {FRONTEND_DIST}")
else:
    logger.info(f"Frontend dist not built; SPA fallback disabled. (Expected at {FRONTEND_DIST})")
