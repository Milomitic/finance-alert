"""Aggregation queries for the dashboard.

All functions are pure: take a Session, return a dataclass. No mutation,
no side effects. Designed to be composed by `app/api/dashboard.py`.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, Index, Stock


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
