"""Tracked-trade positions — lifecycle + read-time live P&L + hit detection.

Closes the playbook → trade loop (B3-6): "Traccia trade" on an alert persists
the playbook's entry/stop/target as a Position row; P&L is enriched READ-TIME
from the live-quote layer (never persisted — a stored P&L is stale within
seconds); stop/target crossings auto-close the position via the same dual-path
piggyback the price-target alerts use (`price_alert_service`):

- `evaluate_intraday_hits` — LIVE path, rides the live-movers sweep tick
  (`app/scheduler/jobs/live_movers_sweep.py`) against live quotes.
- `evaluate_eod_hits`      — EOD path, runs at scan end over stored closes.

Both funnel into `check_stop_target_hits`. Idempotency is structural: a hit
stamps `closed_at`, and only `closed_at IS NULL` rows are ever evaluated —
a closed position can never re-close, whichever path fires first wins.
"""
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Position, Stock

VALID_SIDES = ("long", "short")
VALID_EXIT_REASONS = ("stop", "target", "manual")


def _sign(side: str) -> int:
    """P&L direction multiplier: a short profits when the price FALLS."""
    return 1 if side == "long" else -1


def open_position(
    db: Session,
    *,
    stock_id: int,
    side: str = "long",
    entry_price: float,
    stop_price: float | None = None,
    target_price: float | None = None,
    size: float | None = None,
    alert_id: int | None = None,
    notes: str | None = None,
) -> Position:
    """Persist a new open position. `size` = share count; None = notional-only
    tracking (P&L in % only). Validation is deliberately liberal on stop/entry
    ordering (a stop above entry is a legit locked-in-profit trailing stop for
    a long) — only the stop/target RELATIVE order must match the side, or the
    position would auto-close on its first evaluation tick."""
    if side not in VALID_SIDES:
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")
    if entry_price is None or entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")
    for label, v in (("stop_price", stop_price), ("target_price", target_price)):
        if v is not None and v <= 0:
            raise ValueError(f"{label} must be positive, got {v}")
    if size is not None and size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    if stop_price is not None and target_price is not None:
        if side == "long" and stop_price >= target_price:
            raise ValueError("per un long lo stop deve stare sotto il target")
        if side == "short" and stop_price <= target_price:
            raise ValueError("per uno short lo stop deve stare sopra il target")
    pos = Position(
        stock_id=stock_id,
        alert_id=alert_id,
        side=side,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        size=size,
        notes=notes,
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return pos


def close_position(
    db: Session,
    position_id: int,
    *,
    exit_price: float,
    exit_reason: str = "manual",
) -> Position:
    """Close an OPEN position. Raises LookupError if missing, ValueError if
    already closed (the caller decides whether that's a 409 or a no-op) or on
    invalid exit data. The hit-detection paths never reach the already-closed
    branch — they only select `closed_at IS NULL` rows."""
    pos = db.get(Position, position_id)
    if pos is None:
        raise LookupError(f"position {position_id} not found")
    if pos.closed_at is not None:
        raise ValueError(f"position {position_id} already closed")
    if exit_reason not in VALID_EXIT_REASONS:
        raise ValueError(f"exit_reason invalid: {exit_reason!r}")
    if exit_price is None or exit_price <= 0:
        raise ValueError(f"exit_price must be positive, got {exit_price}")
    pos.closed_at = datetime.now(UTC)
    pos.exit_price = exit_price
    pos.exit_reason = exit_reason
    db.commit()
    db.refresh(pos)
    return pos


def update_position(
    db: Session,
    position_id: int,
    *,
    stop_price: float | None = None,
    target_price: float | None = None,
    notes: str | None = None,
) -> Position:
    """Edit stop/target/notes of an OPEN position (None = leave untouched).
    Editing a closed position makes no sense — ValueError, mapped to 409."""
    pos = db.get(Position, position_id)
    if pos is None:
        raise LookupError(f"position {position_id} not found")
    if pos.closed_at is not None:
        raise ValueError(f"position {position_id} already closed")
    if stop_price is not None:
        if stop_price <= 0:
            raise ValueError("stop_price must be positive")
        pos.stop_price = stop_price
    if target_price is not None:
        if target_price <= 0:
            raise ValueError("target_price must be positive")
        pos.target_price = target_price
    if notes is not None:
        pos.notes = notes
    db.commit()
    db.refresh(pos)
    return pos


def delete_position(db: Session, position_id: int) -> None:
    """Hard delete, open or closed — the user owns the journal; a mistaken
    entry (fat-fingered price) shouldn't pollute the realized history."""
    pos = db.get(Position, position_id)
    if pos is None:
        raise LookupError(f"position {position_id} not found")
    db.delete(pos)
    db.commit()


# ─── Read-time P&L enrichment ────────────────────────────────────────────


def _last_close(db: Session, stock_id: int) -> float | None:
    """Most recent stored daily close — the P&L fallback when no live quote
    is available, and the EOD hit-detection price."""
    bar = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock_id)
            .order_by(OhlcvDaily.date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return float(bar.close) if bar is not None else None


def _live_price(ticker: str) -> float | None:
    """Live price via the shared 10s quote cache. allow_remote_today_fetch=
    False: a list render must never trigger a per-ticker history() call —
    fast_info (cached) is enough; None on any error → caller falls back to
    the stored EOD close."""
    try:
        from app.services import live_quote_service

        q = live_quote_service.get_quote(ticker, allow_remote_today_fetch=False)
    except Exception as exc:  # noqa: BLE001 — one bad quote must not 500 the list
        logger.debug(f"[position] live quote failed for {ticker}: {exc}")
        return None
    if q is None or getattr(q, "error", None) is not None:
        return None
    price = getattr(q, "price", None)
    return float(price) if price is not None else None


def resolve_entry_price(db: Session, stock: Stock) -> float | None:
    """Default entry/exit price when the caller didn't provide one: live
    quote first, last stored close as fallback. None when neither exists."""
    price = _live_price(stock.ticker)
    if price is not None:
        return price
    return _last_close(db, stock.id)


def _enrich(
    db: Session,
    pos: Position,
    stock: Stock,
    *,
    price_fn: Callable[[str], float | None] | None = None,
) -> dict[str, Any]:
    """Serialize one position with read-time P&L. Open positions get
    unrealized P&L from the live quote (EOD-close fallback, `price_source`
    says which); closed ones get realized P&L from the stored exit_price.
    `unrealized_abs`/`realized_abs` are None for notional-only positions
    (size is NULL) — % is the only meaningful number there."""
    entry = float(pos.entry_price)
    size = float(pos.size) if pos.size is not None else None
    sign = _sign(pos.side)
    out: dict[str, Any] = {
        "id": pos.id,
        "stock_id": pos.stock_id,
        "ticker": stock.ticker,
        "name": stock.name,
        "alert_id": pos.alert_id,
        "side": pos.side,
        "entry_price": entry,
        "stop_price": float(pos.stop_price) if pos.stop_price is not None else None,
        "target_price": float(pos.target_price) if pos.target_price is not None else None,
        "size": size,
        "opened_at": pos.opened_at,
        "closed_at": pos.closed_at,
        "exit_price": float(pos.exit_price) if pos.exit_price is not None else None,
        "exit_reason": pos.exit_reason,
        "notes": pos.notes,
        "last_price": None,
        "price_source": None,
        "unrealized_pct": None,
        "unrealized_abs": None,
        "realized_pct": None,
        "realized_abs": None,
    }
    if pos.closed_at is not None:
        if pos.exit_price is not None and entry > 0:
            exit_p = float(pos.exit_price)
            out["realized_pct"] = sign * (exit_p - entry) / entry * 100.0
            if size is not None:
                out["realized_abs"] = sign * (exit_p - entry) * size
        return out
    price = price_fn(stock.ticker) if price_fn is not None else _live_price(stock.ticker)
    source = "live" if price is not None else None
    if price is None:
        price = _last_close(db, pos.stock_id)
        source = "eod" if price is not None else None
    if price is not None and entry > 0:
        out["last_price"] = price
        out["price_source"] = source
        out["unrealized_pct"] = sign * (price - entry) / entry * 100.0
        if size is not None:
            out["unrealized_abs"] = sign * (price - entry) * size
    return out


def list_positions(
    db: Session,
    status: str = "all",
    *,
    price_fn: Callable[[str], float | None] | None = None,
) -> list[dict[str, Any]]:
    """Positions joined with their stock, enriched read-time (see `_enrich`).
    `status`: open | closed | all. `price_fn` is an injectable seam for tests
    (default = the shared live-quote layer)."""
    if status not in ("open", "closed", "all"):
        raise ValueError(f"status must be open|closed|all, got {status!r}")
    stmt = (
        select(Position, Stock)
        .join(Stock, Stock.id == Position.stock_id)
        .order_by(Position.opened_at.desc(), Position.id.desc())
    )
    if status == "open":
        stmt = stmt.where(Position.closed_at.is_(None))
    elif status == "closed":
        stmt = stmt.where(Position.closed_at.is_not(None))
    rows = db.execute(stmt).all()
    return [_enrich(db, pos, stock, price_fn=price_fn) for pos, stock in rows]


def get_position(
    db: Session,
    position_id: int,
    *,
    price_fn: Callable[[str], float | None] | None = None,
) -> dict[str, Any]:
    """One enriched position. LookupError if missing."""
    row = db.execute(
        select(Position, Stock)
        .join(Stock, Stock.id == Position.stock_id)
        .where(Position.id == position_id)
    ).first()
    if row is None:
        raise LookupError(f"position {position_id} not found")
    pos, stock = row
    return _enrich(db, pos, stock, price_fn=price_fn)


# ─── Stop/target hit detection (intraday + EOD paths) ────────────────────


def check_stop_target_hits(
    db: Session,
    price_lookup: Callable[[Stock], float | None],
    *,
    source: str,
    notify: bool = True,
) -> int:
    """Evaluate every OPEN position against `price_lookup(stock)` and close
    the ones whose stop or target was crossed.

    Semantics (side-symmetric, inclusive so a touch counts):
      long:  stop hit when price <= stop; target hit when price >= target
      short: stop hit when price >= stop; target hit when price <= target
    When one observation crosses BOTH (e.g. a gap through an inverted band),
    the stop wins — conservative labeling of an ambiguous fill.

    `exit_price` = the observed crossing price (live tick or EOD close), not
    the stop/target level: gaps through the level fill at the real price.
    Idempotent by construction: closing stamps `closed_at` and only open rows
    are selected. Telegram push on hits is best-effort and never raises.

    Returns: number of positions closed.
    """
    rows = db.execute(
        select(Position, Stock)
        .join(Stock, Stock.id == Position.stock_id)
        .where(Position.closed_at.is_(None))
    ).all()
    if not rows:
        return 0

    closed: list[tuple[Position, Stock]] = []
    now = datetime.now(UTC)
    for pos, stock in rows:
        try:
            price = price_lookup(stock)
        except Exception as exc:  # noqa: BLE001 — one bad ticker must not stop the rest
            logger.debug(f"[position] {source} price lookup failed for {stock.ticker}: {exc}")
            continue
        if price is None:
            continue
        price = float(price)
        sign = _sign(pos.side)
        stop = float(pos.stop_price) if pos.stop_price is not None else None
        target = float(pos.target_price) if pos.target_price is not None else None

        reason: str | None = None
        if stop is not None and sign * (price - stop) <= 0:
            reason = "stop"
        elif target is not None and sign * (price - target) >= 0:
            reason = "target"
        if reason is None:
            continue

        pos.closed_at = now
        pos.exit_price = price
        pos.exit_reason = reason
        closed.append((pos, stock))
        logger.info(
            f"[position] {source} {reason} hit: {stock.ticker} {pos.side} "
            f"entry={float(pos.entry_price):g} exit={price:g}"
        )

    if not closed:
        return 0
    db.commit()

    if notify:
        # Best-effort instant push — a Telegram failure never fails the tick/scan.
        try:
            from app.services import notifier_service

            notifier_service.notify_position_closed(closed)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[position] Telegram push failed (non-fatal): {exc}")
    return len(closed)


def evaluate_intraday_hits(
    db: Session,
    *,
    quote_fn: Callable[[str], Any] | None = None,
    is_open: Callable[[str], bool] | None = None,
    notify: bool = True,
) -> int:
    """LIVE hit-detection path — piggybacks the live-movers sweep tick (same
    pattern as `price_alert_service.evaluate_intraday`). Bounded: only tickers
    with OPEN positions are quoted (typically a handful) and the shared 10s
    quote cache makes a ticker the sweep just covered effectively free.
    Closed-market tickers are skipped — the EOD pass at scan end owns those.

    Seams (`quote_fn`/`is_open`) are injectable for tests."""
    from app.services import live_quote_service

    if quote_fn is None:
        # allow_remote_today_fetch=False: never fire an on-demand history()
        # per ticker from a periodic tick — fast_info (cached 10s) is enough.
        def quote_fn(t: str) -> Any:
            return live_quote_service.get_quote(t, allow_remote_today_fetch=False)
    if is_open is None:
        is_open = live_quote_service._is_market_open

    def lookup(stock: Stock) -> float | None:
        if not is_open(stock.ticker):
            return None
        q = quote_fn(stock.ticker)
        if q is None or getattr(q, "error", None) is not None:
            return None
        price = getattr(q, "price", None)
        return float(price) if price is not None else None

    return check_stop_target_hits(db, lookup, source="intraday", notify=notify)


def evaluate_eod_hits(db: Session, *, notify: bool = True) -> int:
    """EOD hit-detection path — runs at scan end (scan_runner success path)
    over the freshly-stored daily closes, so a stop/target crossed during a
    session with no live sweep coverage (backend down, non-US hours) still
    closes the position the same day the data lands."""
    def lookup(stock: Stock) -> float | None:
        return _last_close(db, stock.id)

    return check_stop_target_hits(db, lookup, source="eod", notify=notify)
