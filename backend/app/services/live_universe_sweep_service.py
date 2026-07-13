"""Rotating universe-wide live top-movers sweep.

The dashboard's live (1G) top-movers re-ranks only a bounded candidate pool
(the union of EOD mover lists), so a stock moving hard intraday that wasn't
already an EOD mover never surfaces — the user's "I looked at a bigger mover
but it doesn't appear" report. This sweep stages live change% for the WHOLE
visible universe so genuine intraday movers can enter the dashboard ranking.

Gentle on yfinance by construction:
  - ROTATING: each tick fetches only the next `chunk` tickers, advancing a
    cursor — full universe covered over several ticks, not in one burst.
  - OPEN-ONLY: tickers whose exchange is currently closed are skipped (no
    intraday move to find, no wasted call).
  - The shared 10s quote cache + the yfinance circuit breaker are the backstop.

State is in-process (module dicts), refreshed by the scheduler job
`run_live_universe_sweep`; read by GET /api/dashboard/live-movers.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.visibility import visible_country_clause
from app.models import Stock

# ticker -> {"change_pct": float, "price": float | None, "ts": epoch}
_CHANGE: dict[str, dict[str, Any]] = {}
_ROT = {"idx": 0}
_LOCK = Lock()


def _now() -> float:
    return time.time()


def _prune(now: float | None = None) -> None:
    now = now if now is not None else _now()
    ttl = settings.live_movers_stale_seconds
    with _LOCK:
        stale = [tk for tk, d in _CHANGE.items() if now - d["ts"] > ttl]
        for tk in stale:
            del _CHANGE[tk]


def record_quotes(quotes: dict[str, Any]) -> int:
    """Stage live change% from a batch of quotes. Returns rows recorded.
    Skips errored / priceless / change-less quotes."""
    now = _now()
    n = 0
    with _LOCK:
        for tk, q in quotes.items():
            if q is None:
                continue
            err = getattr(q, "error", None)
            price = getattr(q, "price", None)
            chg = getattr(q, "change_pct", None)
            if err is not None or price is None or chg is None:
                continue
            _CHANGE[tk] = {"change_pct": float(chg), "price": float(price), "ts": now}
            n += 1
    return n


def get_live_movers(top_n: int | None = None) -> dict[str, Any]:
    """Top gainers + losers by staged live change% (fresh entries only)."""
    top_n = top_n if top_n is not None else settings.live_movers_top_n
    now = _now()
    ttl = settings.live_movers_stale_seconds
    with _LOCK:
        fresh = [
            (tk, d["change_pct"], d.get("price"))
            for tk, d in _CHANGE.items()
            if now - d["ts"] <= ttl
        ]
    gainers = sorted((x for x in fresh if x[1] > 0), key=lambda x: x[1], reverse=True)[:top_n]
    losers = sorted((x for x in fresh if x[1] < 0), key=lambda x: x[1])[:top_n]
    def _fmt(rows):
        return [{"ticker": tk, "change_pct": round(c, 2), "price": p} for tk, c, p in rows]
    return {"gainers": _fmt(gainers), "losers": _fmt(losers), "swept": len(fresh)}


def refresh_chunk(
    db: Session,
    *,
    chunk_size: int | None = None,
    batch_fn: Callable[[list[str]], dict[str, Any]] | None = None,
    is_open: Callable[[str], bool] | None = None,
) -> int:
    """Sweep the next rotating chunk of the universe. Only open-market tickers
    are fetched. Returns the number of quotes staged. Seams (batch_fn/is_open)
    are injectable for tests."""
    from app.services import live_quote_service

    chunk_size = chunk_size or settings.live_movers_chunk
    batch_fn = batch_fn or live_quote_service.get_quotes_batch
    is_open = is_open or live_quote_service._is_market_open

    tickers = [
        t for (t,) in db.execute(
            select(Stock.ticker).where(visible_country_clause()).order_by(Stock.id)
        ).all()
    ]
    if not tickers:
        return 0

    with _LOCK:
        start = _ROT["idx"] % len(tickers)
        _ROT["idx"] = (start + chunk_size) % len(tickers)
    chunk = tickers[start:start + chunk_size]

    open_chunk = [t for t in chunk if is_open(t)]
    if not open_chunk:
        _prune()
        return 0
    try:
        quotes = batch_fn(open_chunk)
    except Exception as exc:  # noqa: BLE001 — never break the scheduler
        logger.warning(f"[live-sweep] batch fetch failed: {exc}")
        return 0
    n = record_quotes(quotes)
    _prune()
    logger.debug(f"[live-sweep] staged {n}/{len(open_chunk)} (cursor→{_ROT['idx']})")
    return n


def clear() -> None:
    """For tests."""
    with _LOCK:
        _CHANGE.clear()
        _ROT["idx"] = 0
