"""APScheduler job: recompute US pre-market top gainers/losers, but
ONLY inside the pre-market window so we don't burn yfinance bandwidth
the other 22 hours a day.

Fires every 5 minutes (cheap no-op outside the window). Work happens
only when, in US/Eastern: it's a weekday, the regular market is NOT
open, and the clock is in the pre-market compute window
(~03:55-09:35 ET — slight padding around Yahoo's 04:00-09:30 session
so the card is warm a few minutes before/after the edges).

The display-side freshness/closed gating lives in
`premarket_service.get_state()`; this job is purely "keep the cache
warm while pre-market data exists".
"""
from datetime import datetime, time

from loguru import logger

from app.core.db import SessionLocal
from app.services import premarket_service
from app.services.premarket_service import _ET

_WINDOW_START = time(3, 55)
_WINDOW_END = time(9, 35)


def run_refresh_premarket() -> None:
    now_et = datetime.now(_ET)
    if now_et.weekday() >= 5:
        return
    if premarket_service.us_market_open_now():
        return
    if not (_WINDOW_START <= now_et.time() < _WINDOW_END):
        return
    db = SessionLocal()
    try:
        premarket_service.refresh(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[refresh_premarket] failed: {exc}")
    finally:
        db.close()
