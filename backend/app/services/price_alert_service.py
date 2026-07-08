"""CRUD + edge-trigger evaluator for price-target alerts.

Two evaluation paths share the same crossing semantics + firing machinery:

- `evaluate_all`      — EOD path, runs at scan end over stored OHLCV closes
                        (prev_close → last_close straddling the target).
- `evaluate_intraday` — LIVE path, piggybacks the live-movers sweep tick and
                        evaluates pending alerts against live quotes so a
                        crossing notifies within ~a minute instead of at the
                        nightly scan. Fires the SAME Alert record and marks
                        `PriceAlert.triggered_at` — the shared idempotency
                        marker — so the later EOD pass can never double-fire.
"""
import json
from datetime import UTC, date, datetime
from typing import Any, Callable

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, PriceAlert, Stock


def list_for_stock(db: Session, stock_id: int) -> list[PriceAlert]:
    return list(
        db.execute(
            select(PriceAlert)
            .where(PriceAlert.stock_id == stock_id)
            .order_by(PriceAlert.created_at.desc())
        ).scalars()
    )


def list_all(db: Session, *, active_only: bool = True) -> list[PriceAlert]:
    """Global listing across all stocks — powers the screener's one-shot
    "campanella" batch fetch (a per-ticker call per row would be N+1 over
    the network). `active_only` keeps only alerts still armed: enabled AND
    not yet triggered (`triggered_at` is the shared idempotency marker of
    both evaluation paths)."""
    stmt = select(PriceAlert).order_by(PriceAlert.created_at.desc())
    if active_only:
        stmt = stmt.where(
            PriceAlert.enabled.is_(True), PriceAlert.triggered_at.is_(None)
        )
    return list(db.execute(stmt).scalars())


def create(
    db: Session,
    stock_id: int,
    target_price: float,
    direction: str,
    note: str | None = None,
) -> PriceAlert:
    if direction not in ("above", "below"):
        raise ValueError(f"direction must be 'above' or 'below', got {direction!r}")
    if target_price <= 0:
        raise ValueError(f"target_price must be positive, got {target_price}")
    pa = PriceAlert(
        stock_id=stock_id,
        target_price=target_price,
        direction=direction,
        note=note,
        enabled=True,
    )
    db.add(pa)
    db.commit()
    db.refresh(pa)
    return pa


def update(
    db: Session,
    alert_id: int,
    *,
    enabled: bool | None = None,
    target_price: float | None = None,
    direction: str | None = None,
    note: str | None = None,
) -> PriceAlert:
    pa = db.get(PriceAlert, alert_id)
    if pa is None:
        raise LookupError(f"price alert {alert_id} not found")
    reset_trigger = False
    if enabled is not None:
        pa.enabled = enabled
    if target_price is not None:
        if target_price <= 0:
            raise ValueError("target_price must be positive")
        pa.target_price = target_price
        reset_trigger = True
    if direction is not None:
        if direction not in ("above", "below"):
            raise ValueError(f"direction invalid: {direction!r}")
        pa.direction = direction
        reset_trigger = True
    if note is not None:
        pa.note = note
    if reset_trigger:
        pa.triggered_at = None
    db.commit()
    db.refresh(pa)
    return pa


def delete(db: Session, alert_id: int) -> None:
    pa = db.get(PriceAlert, alert_id)
    if pa is None:
        raise LookupError(f"price alert {alert_id} not found")
    db.delete(pa)
    db.commit()


def _crossed(direction: str, target: float, prev: float, last: float) -> bool:
    """Edge-trigger crossing semantics — shared by the EOD and intraday paths.
    'above' fires when the price broke UP through the target between the two
    observations; 'below' when it broke DOWN. Strict on `last` so a price
    sitting exactly ON the target doesn't fire (it hasn't crossed yet)."""
    if direction == "above":
        return prev <= target < last
    if direction == "below":
        return prev >= target > last
    return False


def _fire(
    db: Session,
    pa: PriceAlert,
    *,
    prev_close: float,
    last_price: float,
    signal_date: date,
    now: datetime,
    source: str | None = None,
) -> Alert:
    """Create the Alert row for a crossed target and mark the PriceAlert as
    triggered. `pa.triggered_at` is the idempotency marker BOTH evaluation
    paths filter on, so whichever path fires first wins and the other skips.
    Caller commits."""
    snapshot: dict[str, Any] = {
        "price_alert_id": pa.id,
        "target": float(pa.target_price),
        "direction": pa.direction,
        "prev_close": prev_close,
        "last_close": last_price,
    }
    if source:
        # Distinguishes an intraday live-quote fire from the EOD pass in the
        # stored snapshot (the frontend tolerates extra keys).
        snapshot["source"] = source
    alert = Alert(
        stock_id=pa.stock_id,
        trigger_price=last_price,
        snapshot=json.dumps(snapshot),
        signal_date=signal_date,
    )
    db.add(alert)
    pa.triggered_at = now
    return alert


def evaluate_all(db: Session) -> int:
    """Evaluate all enabled, not-yet-triggered price alerts. Fire Alert rows
    for those that crossed their target between prev_close and last_close.

    Returns: number of alerts fired.
    """
    pending = list(
        db.execute(
            select(PriceAlert)
            .where(PriceAlert.enabled.is_(True))
            .where(PriceAlert.triggered_at.is_(None))
        ).scalars()
    )
    fired = 0
    now = datetime.now(UTC)
    for pa in pending:
        bars = list(
            db.execute(
                select(OhlcvDaily)
                .where(OhlcvDaily.stock_id == pa.stock_id)
                .order_by(OhlcvDaily.date.desc())
                .limit(2)
            ).scalars()
        )
        if len(bars) < 2:
            continue
        last_close = float(bars[0].close)
        prev_close = float(bars[1].close)

        if not _crossed(pa.direction, float(pa.target_price), prev_close, last_close):
            continue

        # signal_date = the bar where the price crossed the target. bars[0]
        # is the most recent (DESC ordering above) — that's the bar where
        # `prev_close → last_close` straddled the target threshold.
        _fire(
            db, pa,
            prev_close=prev_close,
            last_price=last_close,
            signal_date=bars[0].date,
            now=now,
        )
        fired += 1

    if fired:
        db.commit()
    return fired


def _prev_session_close(db: Session, stock_id: int) -> float | None:
    """Most recent stored daily close — the intraday path's `prev` reference
    when the live quote didn't carry a usable prev_close."""
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


def evaluate_intraday(
    db: Session,
    *,
    quote_fn: Callable[[str], Any] | None = None,
    is_open: Callable[[str], bool] | None = None,
    notify: bool = True,
) -> int:
    """Evaluate pending price alerts against LIVE prices (intraday path).

    Same crossing semantics as `evaluate_all` but with `last` = live price
    and `prev` = previous session close (from the quote, falling back to the
    stored OHLCV close). Bounded by construction: only tickers with ACTIVE
    (enabled, untriggered) price alerts are quoted — typically a handful —
    and the live-quote layer's 10s cache makes a ticker the sweep just
    covered effectively free.

    Firing sets `PriceAlert.triggered_at` (the marker both paths filter on),
    so a re-tick or the later EOD pass never double-fires. When `notify` is
    True, fired alerts trigger an immediate Telegram push (best-effort — a
    Telegram failure never fails the tick).

    Seams (`quote_fn`/`is_open`) are injectable for tests, mirroring
    `live_universe_sweep_service.refresh_chunk`.
    """
    from app.services import live_quote_service

    if quote_fn is None:
        # allow_remote_today_fetch=False: never fire an on-demand history()
        # per ticker from a periodic tick — fast_info (cached 10s) is enough.
        def quote_fn(t: str) -> Any:
            return live_quote_service.get_quote(t, allow_remote_today_fetch=False)
    if is_open is None:
        is_open = live_quote_service._is_market_open

    rows = db.execute(
        select(PriceAlert, Stock)
        .join(Stock, Stock.id == PriceAlert.stock_id)
        .where(PriceAlert.enabled.is_(True))
        .where(PriceAlert.triggered_at.is_(None))
    ).all()
    if not rows:
        return 0

    fired: list[tuple[Alert, Stock]] = []
    now = datetime.now(UTC)
    for pa, stock in rows:
        # Closed market → no intraday price to evaluate; the EOD pass at scan
        # end owns the close-to-close crossing.
        if not is_open(stock.ticker):
            continue
        try:
            q = quote_fn(stock.ticker)
        except Exception as exc:  # noqa: BLE001 — one bad ticker must not stop the rest
            logger.debug(f"[price-alert] intraday quote failed for {stock.ticker}: {exc}")
            continue
        if q is None or getattr(q, "error", None) is not None:
            continue
        price = getattr(q, "price", None)
        if price is None:
            continue
        prev = getattr(q, "prev_close", None)
        if prev is None:
            prev = _prev_session_close(db, pa.stock_id)
        if prev is None:
            continue
        if not _crossed(pa.direction, float(pa.target_price), float(prev), float(price)):
            continue

        # signal_date = the trading day of the crossing, in the exchange's
        # local calendar (UTC date would mislabel e.g. an ASX morning).
        try:
            sig_date = live_quote_service._market_today(stock.ticker)
        except Exception:  # noqa: BLE001 — tz lookup must never block a fire
            sig_date = now.date()
        alert = _fire(
            db, pa,
            prev_close=float(prev),
            last_price=float(price),
            signal_date=sig_date,
            now=now,
            source="intraday",
        )
        fired.append((alert, stock))
        logger.info(
            f"[price-alert] intraday fire: {stock.ticker} {pa.direction} "
            f"target={float(pa.target_price):g} price={float(price):g}"
        )

    if not fired:
        return 0
    db.commit()

    if notify:
        # Best-effort instant push — never let Telegram break the sweep tick.
        try:
            from app.services import notifier_service

            notifier_service.notify_price_alerts(fired)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[price-alert] intraday Telegram push failed (non-fatal): {exc}")
    return len(fired)
