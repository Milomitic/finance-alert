"""CRUD + edge-trigger evaluator for price-target alerts."""
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, PriceAlert


def list_for_stock(db: Session, stock_id: int) -> list[PriceAlert]:
    return list(
        db.execute(
            select(PriceAlert)
            .where(PriceAlert.stock_id == stock_id)
            .order_by(PriceAlert.created_at.desc())
        ).scalars()
    )


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
        target = float(pa.target_price)

        crossed = False
        if pa.direction == "above" and prev_close <= target < last_close:
            crossed = True
        elif pa.direction == "below" and prev_close >= target > last_close:
            crossed = True

        if not crossed:
            continue

        snapshot = {
            "price_alert_id": pa.id,
            "target": target,
            "direction": pa.direction,
            "prev_close": prev_close,
            "last_close": last_close,
        }
        # signal_date = the bar where the price crossed the target. bars[0]
        # is the most recent (DESC ordering above) — that's the bar where
        # `prev_close → last_close` straddled the target threshold.
        db.add(
            Alert(
                rule_id=None,
                stock_id=pa.stock_id,
                trigger_price=last_close,
                snapshot=json.dumps(snapshot),
                signal_date=bars[0].date,
            )
        )
        pa.triggered_at = now
        fired += 1

    if fired:
        db.commit()
    return fired
