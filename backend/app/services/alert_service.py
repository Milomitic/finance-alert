"""Alert query and mutation service."""
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy
from sqlalchemy import Float, and_, asc, desc, func, or_, select, update
from sqlalchemy.orm import Session

from app.models import Alert, Stock

# Columns that the caller may request sorting on.
# confidence/tone live inside Alert.snapshot (SQLite JSON text column) and
# are extracted at query time via json_extract so they sort correctly across
# all rows regardless of pagination.
_SORTABLE: dict[str, Any] = {
    "triggered_at": Alert.triggered_at,
    "signal_date": Alert.signal_date,
    "ticker": Stock.ticker,
    "trigger_price": Alert.trigger_price,
    "kind": Alert.signal_name,
    "confidence": sqlalchemy.cast(
        func.json_extract(Alert.snapshot, "$.confidence"), Float
    ),
    "tone": func.json_extract(Alert.snapshot, "$.tone"),
}
_SORTABLE_KEYS = frozenset(_SORTABLE)


def derive_rule_kind(rule_kind: str | None, signal_name: str | None) -> str | None:
    """The UI 'kind' for an alert. Signal-engine alerts use f'signal:{signal_name}'.
    Returns None only for the (currently impossible) case of neither — the frontend
    already tolerates a null kind."""
    if rule_kind is not None:
        return rule_kind
    if signal_name:
        return f"signal:{signal_name}"
    return None


def _apply_filters(
    stmt,
    *,
    ticker: str | None = None,
    q: str | None = None,
    rule_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    read: bool | None = None,
    archived: bool | None = None,
):
    if ticker:
        stmt = stmt.where(func.lower(Stock.ticker) == ticker.lower())
    # `q` is the new column-header search field — substring match on
    # either ticker or name. Replaces the standalone Ticker filter
    # input that the AlertFilters card used to host.
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Stock.ticker).like(like),
                func.lower(Stock.name).like(like),
            )
        )
    if rule_kind:
        name = rule_kind[len("signal:"):] if rule_kind.startswith("signal:") else rule_kind
        stmt = stmt.where(Alert.signal_name == name)
    if date_from:
        stmt = stmt.where(Alert.triggered_at >= date_from)
    if date_to:
        stmt = stmt.where(Alert.triggered_at < date_to)
    if read is True:
        stmt = stmt.where(Alert.read_at.isnot(None))
    elif read is False:
        stmt = stmt.where(Alert.read_at.is_(None))
    if archived is True:
        stmt = stmt.where(Alert.archived_at.isnot(None))
    elif archived is False:
        stmt = stmt.where(Alert.archived_at.is_(None))
    return stmt


def list_alerts(
    db: Session,
    *,
    ticker: str | None = None,
    q: str | None = None,
    rule_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    read: bool | None = None,
    archived: bool | None = False,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "triggered_at",
    sort_dir: str = "desc",
) -> tuple[list[dict[str, Any]], int, bool]:
    """List alerts with stock.ticker. Returns (items, total, has_more)."""
    limit = max(1, min(limit, 500))
    base = (
        select(
            Alert,
            Stock.ticker.label("ticker"),
            Stock.name.label("name"),
        )
        .join(Stock, Stock.id == Alert.stock_id)
    )
    base = _apply_filters(
        base,
        ticker=ticker,
        q=q,
        rule_kind=rule_kind,
        date_from=date_from,
        date_to=date_to,
        read=read,
        archived=archived,
    )
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int(db.execute(count_stmt).scalar_one())
    # Build ORDER BY: requested column (with NULLS LAST) + stable id tiebreaker.
    sort_col = _SORTABLE.get(sort_by, Alert.triggered_at)
    direction = asc if sort_dir == "asc" else desc
    rows = db.execute(
        base.order_by(direction(sort_col).nullslast(), Alert.id.desc()).limit(limit + 1).offset(offset)
    ).all()
    has_more = len(rows) > limit
    items = []
    for alert, ticker_val, name_val in rows[:limit]:
        items.append(
            {
                "id": alert.id,
                "rule_kind": derive_rule_kind(None, alert.signal_name),
                "stock_id": alert.stock_id,
                "ticker": ticker_val,
                "name": name_val,
                "triggered_at": alert.triggered_at,
                "signal_date": alert.signal_date,
                "trigger_price": float(alert.trigger_price),
                "snapshot": alert.snapshot,
                "read_at": alert.read_at,
                "archived_at": alert.archived_at,
            }
        )
    return items, total, has_more


def get_alert(db: Session, alert_id: int) -> Alert | None:
    return db.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()


def patch_alert(
    db: Session, alert_id: int, *, read: bool | None = None, archived: bool | None = None
) -> Alert | None:
    a = get_alert(db, alert_id)
    if a is None:
        return None
    now = datetime.now(UTC)
    if read is True:
        a.read_at = now
    elif read is False:
        a.read_at = None
    if archived is True:
        a.archived_at = now
    elif archived is False:
        a.archived_at = None
    db.commit()
    db.refresh(a)
    return a


def bulk_action(db: Session, ids: list[int], action: str) -> int:
    """Apply bulk action (mark_read, mark_unread, archive, unarchive). Returns affected count."""
    if not ids:
        return 0
    now = datetime.now(UTC)
    if action == "mark_read":
        stmt = update(Alert).where(Alert.id.in_(ids)).values(read_at=now)
    elif action == "mark_unread":
        stmt = update(Alert).where(Alert.id.in_(ids)).values(read_at=None)
    elif action == "archive":
        stmt = update(Alert).where(Alert.id.in_(ids)).values(archived_at=now)
    elif action == "unarchive":
        stmt = update(Alert).where(Alert.id.in_(ids)).values(archived_at=None)
    else:
        raise ValueError(f"unknown action: {action}")
    res = db.execute(stmt)
    db.commit()
    return res.rowcount or 0


def unread_count(db: Session) -> int:
    return int(
        db.execute(
            select(func.count(Alert.id)).where(
                and_(Alert.read_at.is_(None), Alert.archived_at.is_(None))
            )
        ).scalar_one()
    )
