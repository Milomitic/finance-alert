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
