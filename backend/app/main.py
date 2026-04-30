"""FastAPI application entry point."""
from fastapi import FastAPI

from app.api import auth as auth_router
from app.api import stocks as stocks_router
from app.api import watchlists as watchlists_router

app = FastAPI(title="Finance Alert", version="0.1.0")
app.include_router(auth_router.router)
app.include_router(stocks_router.router)
app.include_router(watchlists_router.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "version": app.version}
