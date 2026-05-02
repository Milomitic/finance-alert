"""Aggregation queries for the dashboard.

All functions are pure: take a Session, return a dataclass. No mutation,
no side effects. Designed to be composed by `app/api/dashboard.py`.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, Index, Rule, Stock


@dataclass
class KpiSummary:
    alerts_last_24h: int
    alerts_prev_24h: int
    alerts_unread: int
    stocks_monitored: int
    indices_count: int


def get_kpi_summary(db: Session) -> KpiSummary:
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    last_24h = db.execute(
        select(func.count(Alert.id)).where(
            Alert.triggered_at > cutoff_24h,
            Alert.archived_at.is_(None),
        )
    ).scalar_one()

    prev_24h = db.execute(
        select(func.count(Alert.id)).where(
            Alert.triggered_at > cutoff_48h,
            Alert.triggered_at <= cutoff_24h,
            Alert.archived_at.is_(None),
        )
    ).scalar_one()

    unread = db.execute(
        select(func.count(Alert.id)).where(
            Alert.read_at.is_(None),
            Alert.archived_at.is_(None),
        )
    ).scalar_one()

    stocks_count = db.execute(select(func.count(Stock.id))).scalar_one()
    indices_count = db.execute(select(func.count(Index.id))).scalar_one()

    return KpiSummary(
        alerts_last_24h=int(last_24h),
        alerts_prev_24h=int(prev_24h),
        alerts_unread=int(unread),
        stocks_monitored=int(stocks_count),
        indices_count=int(indices_count),
    )


@dataclass
class AlertsByDayPoint:
    date: date  # python date
    count: int
    by_kind: dict[str, int]


def get_alerts_by_day(db: Session, days: int = 30) -> list[AlertsByDayPoint]:
    """Return one point per day in the [today - days + 1, today] range, ascending.

    Days with no alerts are included with count=0 and by_kind={}, so the chart
    is continuous (no gaps).
    """
    today = date.today()
    start_day = today - timedelta(days=days - 1)
    cutoff_dt = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)

    rows = db.execute(
        select(
            func.date(Alert.triggered_at).label("d"),
            Rule.kind.label("kind"),
            func.count(Alert.id).label("c"),
        )
        .join(Rule, Rule.id == Alert.rule_id)
        .where(
            Alert.triggered_at >= cutoff_dt,
            Alert.archived_at.is_(None),
        )
        .group_by("d", Rule.kind)
    ).all()

    by_date: dict[date, dict[str, int]] = {}
    for d, kind, c in rows:
        # SQLite returns str from func.date(); Postgres returns date.
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        by_date.setdefault(d, {})[kind] = int(c)

    points: list[AlertsByDayPoint] = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        kinds = by_date.get(day, {})
        points.append(
            AlertsByDayPoint(date=day, count=sum(kinds.values()), by_kind=kinds)
        )
    return points


@dataclass
class TopStock:
    stock_id: int
    ticker: str
    alert_count: int
    top_kind: str | None


def get_top_stocks(db: Session, *, days: int = 30, limit: int = 10) -> list[TopStock]:
    """Return up to `limit` stocks with the most alerts in the last `days` days.

    Order: alert_count DESC, ticker ASC (deterministic tie-break).
    `top_kind` = most frequent rule.kind for that stock in the same window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Step 1: top stock_ids by count
    counts = db.execute(
        select(
            Alert.stock_id,
            func.count(Alert.id).label("c"),
        )
        .where(Alert.triggered_at >= cutoff, Alert.archived_at.is_(None))
        .group_by(Alert.stock_id)
        .order_by(func.count(Alert.id).desc(), Alert.stock_id.asc())
        .limit(limit)
    ).all()

    if not counts:
        return []

    stock_ids = [row.stock_id for row in counts]
    tickers = {
        s.id: s.ticker
        for s in db.execute(select(Stock).where(Stock.id.in_(stock_ids))).scalars().all()
    }

    # Step 2: top kind per stock (subquery LIMIT 1 each)
    top_kind_by_stock: dict[int, str] = {}
    for sid in stock_ids:
        kind_row = db.execute(
            select(Rule.kind, func.count(Alert.id).label("c"))
            .join(Alert, Alert.rule_id == Rule.id)
            .where(
                Alert.stock_id == sid,
                Alert.triggered_at >= cutoff,
                Alert.archived_at.is_(None),
            )
            .group_by(Rule.kind)
            .order_by(func.count(Alert.id).desc(), Rule.kind.asc())
            .limit(1)
        ).first()
        if kind_row is not None:
            top_kind_by_stock[sid] = kind_row.kind

    # Compose, preserving the ordering from step 1 but re-sorted by ticker tie-break
    enriched = sorted(
        [(row.stock_id, int(row.c), tickers.get(row.stock_id, "")) for row in counts],
        key=lambda t: (-t[1], t[2]),
    )
    result: list[TopStock] = []
    for stock_id, c, ticker in enriched:
        result.append(
            TopStock(
                stock_id=stock_id,
                ticker=ticker,
                alert_count=c,
                top_kind=top_kind_by_stock.get(stock_id),
            )
        )
    return result


@dataclass
class SystemStatus:
    scheduler_running: bool
    scan_alerts_next_run: datetime | None
    send_digest_next_run: datetime | None
    refresh_catalog_next_run: datetime | None
    telegram_configured: bool
    last_digest_sent_at: datetime | None  # always None until a digest audit log is added (out of scope for 3A/3A-bis/3B)


def get_system_status(db: Session) -> SystemStatus:
    from app.core.config import settings
    from app.scheduler import get_scheduler

    sched = get_scheduler()
    next_runs: dict[str, datetime | None] = {}
    for job_id in ("scan_alerts", "send_digest", "refresh_catalog"):
        job = sched.get_job(job_id)
        if job is None:
            next_runs[job_id] = None
        else:
            next_runs[job_id] = getattr(job, "next_run_time", None)

    return SystemStatus(
        scheduler_running=sched.running,
        scan_alerts_next_run=next_runs["scan_alerts"],
        send_digest_next_run=next_runs["send_digest"],
        refresh_catalog_next_run=next_runs["refresh_catalog"],
        telegram_configured=bool(settings.telegram_bot_token) and bool(settings.telegram_chat_id),
        last_digest_sent_at=None,
    )
