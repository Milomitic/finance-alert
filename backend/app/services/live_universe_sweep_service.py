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


_ALWAYS_WARM: tuple[str, ...] | None = None


def _always_warm_symbols() -> tuple[str, ...]:
    """The dashboard's indices / commodities / crypto, plus their futures pairs.

    Lazy import on purpose: the list lives in the API layer because it carries
    display metadata (name, flag, category), and importing it at module level
    here would invert the service → api dependency at load time."""
    global _ALWAYS_WARM
    if _ALWAYS_WARM is None:
        from app.api.market import LIVE_ASSET_DEFINITIONS

        syms = [d[0] for d in LIVE_ASSET_DEFINITIONS]
        syms += [d[4] for d in LIVE_ASSET_DEFINITIONS if d[4]]
        _ALWAYS_WARM = tuple(dict.fromkeys(syms))
    return _ALWAYS_WARM


def _warm_live_assets(
    batch_fn: Callable[[list[str]], dict[str, Any]],
    is_open: Callable[[str], bool],
    has_value: Callable[[str], bool],
) -> None:
    """Keep a floor under the dashboard's first panel.

    These symbols are deliberately absent from the `Stock` catalog — they are
    not equities the user follows — so the rotation below never reaches them.
    They also have no rows in `ohlcv_daily`. The consequence is that EVERY rung
    of the live-quote fallback ladder is empty for them: no warm cache, no
    last-good, no L2 snapshot, no EOD close. When a live fetch misses the
    interactive deadline there is simply nothing to show, and the panel renders
    "—" for all of them at once — which is exactly what it did.

    Warming them here fixes that at the source: the sweep runs on the
    background pool with no deadline, so it lands the quotes that the
    user-facing path can then serve instantly or fall back to.

    Every tick, not on the rotation: it is ~18 symbols, and they are the first
    thing on the page. They are NOT passed to `record_quotes` — an index is
    not a "mover" and would pollute that list.

    Open markets are refreshed; a CLOSED one is fetched only when we hold
    nothing for it at all.

    The first version gated purely on `is_open`, reasoning that once a
    session's quotes are flushed to L2 they stay the correct floor while the
    market is shut. True — as long as they were ever warmed WHILE open. From
    cold the rule excludes itself: a pod that starts after Milan and Shanghai
    have closed never warms them, L2 has nothing, and those two rows stay
    blank until the next session opens. That is exactly what shipped, and the
    dashboard showed it precisely — every open market populated, and only
    FTSE MIB and CSI 300 (the two closed ones without a futures pair) empty.

    So the condition is open OR cold. A closed market's last price is the
    right thing to display, it costs one request per symbol per process, and
    once held the `has_any_value` check stops asking again.
    """
    warm = [
        s
        for s in _always_warm_symbols()
        if is_open(s) or not has_value(s)
    ]
    if not warm:
        return
    try:
        batch_fn(warm)
    except Exception as exc:  # noqa: BLE001 — never break the sweep or scheduler
        logger.warning(f"[live-sweep] live-asset warm failed: {exc}")


def refresh_chunk(
    db: Session,
    *,
    chunk_size: int | None = None,
    batch_fn: Callable[[list[str]], dict[str, Any]] | None = None,
    is_open: Callable[[str], bool] | None = None,
    has_value: Callable[[str], bool] | None = None,
) -> int:
    """Sweep the next rotating chunk of the universe. Only open-market tickers
    are fetched. Returns the number of quotes staged. Seams (batch_fn/is_open)
    are injectable for tests."""
    from app.services import live_quote_service

    chunk_size = chunk_size or settings.live_movers_chunk
    # deadline_seconds=None: this is the BACKGROUND pool — nobody is waiting on
    # it, and its whole job is to actually land the quotes that keep the
    # user-facing path warm. The 6s deadline exists to protect interactive
    # requests; applying it here would make the sweep give up on the very
    # tickers it exists to fetch.
    batch_fn = batch_fn or (
        lambda tickers: live_quote_service.get_quotes_batch(tickers, deadline_seconds=None)
    )
    is_open = is_open or live_quote_service._is_market_open
    has_value = has_value or live_quote_service.has_any_value

    _warm_live_assets(batch_fn, is_open, has_value)

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
