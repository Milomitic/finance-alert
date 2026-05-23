"""Daily scan: fetch OHLCV per stock, run the signal engine,
fire edge-deduped signal alerts.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.visibility import visible_country_clause
from app.models import Alert, OhlcvDaily, Stock
from app.signals.signal_scan_service import evaluate_signals


@dataclass
class ScanResult:
    stocks_scanned: int = 0
    stocks_skipped: int = 0
    alerts_fired: int = 0
    states_updated: int = 0


def _load_ohlcv(db: Session, stock_id: int, limit: int = 260) -> pd.DataFrame | None:
    rows = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock_id)
            .order_by(OhlcvDaily.date.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    rows = rows[-limit:]
    return pd.DataFrame(
        {
            "date": [r.date for r in rows],
            "open": [float(r.open) for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [int(r.volume) for r in rows],
        }
    )


class ScanCancelled(RuntimeError):
    """Raised when the cancel_check callback returned True between iterations.
    The runner catches this and marks the ScanRun row as 'failed' with a clear
    user-cancel message (distinct from a crash)."""


def scan_universe(
    db: Session,
    *,
    on_progress: Callable[[int, int, "ScanResult", str | None], None] | None = None,
    progress_every: int = 10,
    cancel_check: Callable[[], bool] | None = None,
) -> ScanResult:
    """Scan all stocks, run the signal engine, fire edge-deduped signal alerts.

    on_progress, if provided, is called every `progress_every` stocks AND at start/end
    with (stocks_done, stocks_total, result_so_far, current_ticker). Use this to
    surface live progress to a UI (e.g. by updating a `scan_runs` row). The
    `current_ticker` arg is the ticker most recently processed (or about to be
    processed at the start tick); None at the bookend calls when no specific
    stock is in focus.

    cancel_check, if provided, is called at the same cadence as on_progress.
    When it returns True the loop raises ScanCancelled so the caller can mark
    the run as user-cancelled. The check is O(1) (in-memory set membership)
    so the overhead is negligible.
    """
    result = ScanResult()
    # Skip catalog-only countries (CN/JP/KR) from alert generation —
    # they live in DB only to feed dashboard breadth + Asia mood.
    # Single source of truth: `app.core.visibility`.
    stocks = list(
        db.execute(select(Stock).where(visible_country_clause()))
        .scalars()
        .all()
    )
    total = len(stocks)

    if on_progress:
        on_progress(0, total, result, None)

    for idx, stock in enumerate(stocks, start=1):
        # Cooperative cancel: bail out cleanly between iterations. We check at
        # the same cadence as on_progress to keep the overhead bounded; a per-
        # iteration check would be ~110× more frequent for the 1132-stock
        # universe but adds no real responsiveness for the user.
        if cancel_check is not None and (idx % progress_every == 1 or idx == 1):
            if cancel_check():
                logger.info(
                    f"[scan] cancel requested at idx={idx}/{total} — aborting cleanly"
                )
                raise ScanCancelled("Cancellato dall'utente")

        ohlcv = _load_ohlcv(db, stock.id)
        if ohlcv is None or len(ohlcv) < 2:
            result.stocks_skipped += 1
            if on_progress and (idx % progress_every == 0 or idx == total):
                on_progress(idx, total, result, stock.ticker)
            continue
        result.stocks_scanned += 1

        # Signal engine — the only alert source.
        try:
            result.alerts_fired += evaluate_signals(db, stock, ohlcv)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[scan] signals failed for {stock.ticker}: {e}")

        if on_progress and (idx % progress_every == 0 or idx == total):
            on_progress(idx, total, result, stock.ticker)

    if on_progress:
        on_progress(total, total, result, None)

    logger.info(
        f"[scan] complete: scanned={result.stocks_scanned} skipped={result.stocks_skipped} "
        f"alerts={result.alerts_fired}"
    )
    return result
