"""APScheduler job: one rotating chunk of the universe-wide live-movers sweep.

Runs frequently (every ~75s) but does little each tick — only the next chunk
of open-market tickers — so the dashboard's live top-movers can reflect genuine
intraday movers across the WHOLE universe without hammering yfinance.
"""
from loguru import logger

from app.core.db import SessionLocal
from app.services import live_universe_sweep_service


def run_live_universe_sweep() -> None:
    db = SessionLocal()
    try:
        live_universe_sweep_service.refresh_chunk(db)
    except Exception as exc:  # noqa: BLE001 — never break the scheduler loop
        logger.warning(f"[live-sweep] job failed: {exc}")
    finally:
        db.close()
