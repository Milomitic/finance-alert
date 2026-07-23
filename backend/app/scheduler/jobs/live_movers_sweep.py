"""APScheduler job: one rotating chunk of the universe-wide live-movers sweep.

Runs frequently (every ~75s) but does little each tick — only the next chunk
of open-market tickers — so the dashboard's live top-movers can reflect genuine
intraday movers across the WHOLE universe without hammering yfinance.

The tick also piggybacks the INTRADAY price-target evaluation: pending price
alerts are checked against live quotes so a crossing notifies within ~a minute
instead of waiting for the nightly EOD scan. Bounded (only tickers with active
alerts are quoted; the shared 10s quote cache makes swept ones free) and
best-effort — neither step may break the scheduler loop or the other.
"""
from loguru import logger

from app.core.db import SessionLocal
from app.services import (
    live_quote_service,
    live_universe_sweep_service,
    position_service,
    price_alert_service,
)


def run_live_universe_sweep() -> None:
    db = SessionLocal()
    try:
        try:
            live_universe_sweep_service.refresh_chunk(db)
        except Exception as exc:  # noqa: BLE001 — never break the scheduler loop
            logger.warning(f"[live-sweep] job failed: {exc}")
        # Intraday price-target evaluation — independent of the sweep chunk
        # outcome (an alert ticker may be open even when the whole chunk was
        # closed-market), idempotent vs the EOD pass via PriceAlert.triggered_at.
        try:
            price_alert_service.evaluate_intraday(db)
        except Exception as exc:  # noqa: BLE001 — never break the scheduler loop
            logger.warning(f"[live-sweep] intraday price-alert eval failed: {exc}")
        # Intraday stop/target hit detection for tracked positions — same
        # bounded piggyback (only tickers with OPEN positions are quoted),
        # idempotent vs the EOD pass via Position.closed_at.
        try:
            position_service.evaluate_intraday_hits(db)
        except Exception as exc:  # noqa: BLE001 — never break the scheduler loop
            logger.warning(f"[live-sweep] intraday position hit-check failed: {exc}")
        # Persist what this pass warmed, in ONE transaction. This is what makes
        # the app fast on the FIRST load after a restart: without it the L1
        # quote cache boots empty and the landing page cold-fans-out to Yahoo.
        try:
            live_quote_service.flush_l2()
        except Exception as exc:  # noqa: BLE001 — never break the scheduler loop
            logger.warning(f"[live-sweep] L2 quote flush failed: {exc}")
    finally:
        db.close()
