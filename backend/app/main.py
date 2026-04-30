"""FastAPI application entry point."""
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
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
app.include_router(catalog_router.router)
app.include_router(stocks_router.router)
app.include_router(watchlists_router.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "scheduler_running": get_scheduler().running, "version": app.version}
