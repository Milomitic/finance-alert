"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from fastapi import FastAPI

from app.api import auth as auth_router
from app.api import stocks as stocks_router
from app.api import watchlists as watchlists_router
from app.scheduler import get_scheduler, start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="Finance Alert", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(stocks_router.router)
app.include_router(watchlists_router.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "scheduler_running": get_scheduler().running, "version": app.version}
