"""Alert query and mutation service."""
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy
from sqlalchemy import Float, asc, desc, func, or_, select, update
from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome, Stock

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
    # Two-score model. "strength" (Forza) = COALESCE($.strength, $.confidence) so
    # legacy alerts (confidence-only) still sort. "probability" (Probabilita).
    "strength": func.coalesce(
        sqlalchemy.cast(func.json_extract(Alert.snapshot, "$.strength"), Float),
        sqlalchemy.cast(func.json_extract(Alert.snapshot, "$.confidence"), Float),
    ),
    "probability": sqlalchemy.cast(
        func.json_extract(Alert.snapshot, "$.probability"), Float
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


# Signal "nature": continuation (trend-following) vs reversal (mean-reversion).
# chart_pattern is mixed (triangle=continuation, double-top/bottom=reversal) and
# is intentionally excluded from both sets; the UI badge classifies it precisely
# from the chain, but the coarse server-side filter leaves it out.
_CONTINUATION_SIGNALS = {
    "volume_breakout", "high52_momentum", "trend_pullback", "squeeze_expansion",
    "gap_and_go", "adx_confirmation", "sr_flip", "structure_break",
    "hidden_divergence", "pead", "analyst_momentum",
}
_REVERSAL_SIGNALS = {
    "rsi_divergence", "macd_divergence", "oversold_reversal", "candle_reversal",
    "insider_buy",
}


def _apply_filters(
    stmt,
    *,
    ticker: str | None = None,
    q: str | None = None,
    rule_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: bool | None = None,
    tone: str | None = None,
    confidence_min: float | None = None,
    strength_min: float | None = None,
    probability_min: float | None = None,
    nature: str | None = None,
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
    if archived is True:
        stmt = stmt.where(Alert.archived_at.isnot(None))
    elif archived is False:
        stmt = stmt.where(Alert.archived_at.is_(None))
    if tone is not None:
        stmt = stmt.where(func.json_extract(Alert.snapshot, "$.tone") == tone)
    if confidence_min is not None:
        stmt = stmt.where(
            sqlalchemy.cast(func.json_extract(Alert.snapshot, "$.confidence"), Float)
            >= confidence_min
        )
    if strength_min is not None:
        stmt = stmt.where(
            func.coalesce(
                sqlalchemy.cast(func.json_extract(Alert.snapshot, "$.strength"), Float),
                sqlalchemy.cast(func.json_extract(Alert.snapshot, "$.confidence"), Float),
            ) >= strength_min
        )
    if probability_min is not None:
        stmt = stmt.where(
            sqlalchemy.cast(func.json_extract(Alert.snapshot, "$.probability"), Float)
            >= probability_min
        )
    if nature == "continuazione":
        stmt = stmt.where(Alert.signal_name.in_(_CONTINUATION_SIGNALS))
    elif nature == "inversione":
        stmt = stmt.where(Alert.signal_name.in_(_REVERSAL_SIGNALS))
    return stmt


def _next_earnings_dates_cached(tickers: set[str]) -> dict[str, date]:
    """{ticker: next_earnings_date} for the given tickers, CACHE-ONLY.

    Reads `stock_fundamentals_service._CACHE` directly (same pattern as
    `calendar_service._earnings_for_stock` — see the two-tier-cache note in
    CLAUDE.md): NEVER triggers a yfinance roundtrip from the alerts list
    path. A cold/missing cache entry (or an unparsable date) is simply
    absent from the result → the API field stays null and the UI hides the
    earnings-proximity badge. Lazy import keeps the alerts module light.
    """
    from app.services import stock_fundamentals_service

    out: dict[str, date] = {}
    for t in tickers:
        cached = stock_fundamentals_service._CACHE.get(t)
        raw = cached.next_earnings_date if cached is not None else None
        if not raw:
            continue
        try:
            out[t] = date.fromisoformat(str(raw)[:10])
        except (ValueError, TypeError):
            continue
    return out


def list_alerts(
    db: Session,
    *,
    ticker: str | None = None,
    q: str | None = None,
    rule_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: bool | None = False,
    tone: str | None = None,
    confidence_min: float | None = None,
    strength_min: float | None = None,
    probability_min: float | None = None,
    nature: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "triggered_at",
    sort_dir: str = "desc",
) -> tuple[list[dict[str, Any]], int, bool]:
    """List alerts with stock.ticker. Returns (items, total, has_more)."""
    limit = max(1, min(limit, 500))
    # LEFT OUTER JOIN on the outcome warehouse: at most ONE row per alert
    # (unique index on signal_outcomes.alert_id), so the join can't fan out
    # the count or the pagination. Matured signal alerts carry their realised
    # forward outcome; pending/legacy/price alerts get NULLs.
    base = (
        select(
            Alert,
            Stock.ticker.label("ticker"),
            Stock.name.label("name"),
            SignalOutcome.abs_hit.label("outcome_abs_hit"),
            SignalOutcome.fwd_return.label("outcome_fwd_return"),
            SignalOutcome.horizon_days.label("outcome_horizon_days"),
            SignalOutcome.mkt_neutral_excess.label("outcome_mkt_excess"),
        )
        .join(Stock, Stock.id == Alert.stock_id)
        .outerjoin(SignalOutcome, SignalOutcome.alert_id == Alert.id)
    )
    base = _apply_filters(
        base,
        ticker=ticker,
        q=q,
        rule_kind=rule_kind,
        date_from=date_from,
        date_to=date_to,
        archived=archived,
        tone=tone,
        confidence_min=confidence_min,
        strength_min=strength_min,
        probability_min=probability_min,
        nature=nature,
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
    page = rows[:limit]
    # Earnings-proximity substrate: one cache-only dict pass over the page's
    # distinct tickers (≤ `limit` lookups, no DB, no network).
    earnings_by_ticker = _next_earnings_dates_cached(
        {ticker_val for _, ticker_val, *_ in page if ticker_val}
    )
    items = []
    for alert, ticker_val, name_val, o_hit, o_fwd, o_horizon, o_mkt in page:
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
                # Realised outcome (signal_outcomes warehouse). All None while
                # the signal is still maturing (or for legacy/price alerts) —
                # the UI shows "in corso" for pending signal alerts.
                "outcome_hit": bool(o_hit) if o_hit is not None else None,
                "outcome_fwd_return": round(float(o_fwd), 4) if o_fwd is not None else None,
                "outcome_horizon_days": int(o_horizon) if o_horizon is not None else None,
                "outcome_mkt_excess": round(float(o_mkt), 4) if o_mkt is not None else None,
                # Earnings-proximity risk flag (cache-only; null when the
                # fundamentals cache is cold for the ticker).
                "next_earnings_date": earnings_by_ticker.get(ticker_val),
            }
        )
    return items, total, has_more


def get_alert(db: Session, alert_id: int) -> Alert | None:
    return db.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()


def patch_alert(
    db: Session, alert_id: int, *, archived: bool | None = None
) -> Alert | None:
    a = get_alert(db, alert_id)
    if a is None:
        return None
    now = datetime.now(UTC)
    if archived is True:
        a.archived_at = now
    elif archived is False:
        a.archived_at = None
    db.commit()
    db.refresh(a)
    return a


def bulk_action(db: Session, ids: list[int], action: str) -> int:
    """Apply bulk action (archive, unarchive). Returns affected count."""
    if not ids:
        return 0
    now = datetime.now(UTC)
    if action == "archive":
        stmt = update(Alert).where(Alert.id.in_(ids)).values(archived_at=now)
    elif action == "unarchive":
        stmt = update(Alert).where(Alert.id.in_(ids)).values(archived_at=None)
    else:
        raise ValueError(f"unknown action: {action}")
    res = db.execute(stmt)
    db.commit()
    return res.rowcount or 0
