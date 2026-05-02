"""Pydantic schemas for the dashboard summary endpoint."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.alert import AlertOut, ScanStatusOut


class KpiSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alerts_last_24h: int
    alerts_prev_24h: int
    alerts_unread: int
    stocks_monitored: int
    indices_count: int
    last_scan: ScanStatusOut | None
    next_scan_at: datetime | None
    next_digest_at: datetime | None


class AlertsByDayPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    count: int
    by_kind: dict[str, int]


class TopStockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stock_id: int
    ticker: str
    name: str | None = None
    alert_count: int
    top_kind: str | None


class SystemStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduler_running: bool
    scan_alerts_next_run: datetime | None
    send_digest_next_run: datetime | None
    refresh_catalog_next_run: datetime | None
    telegram_configured: bool
    last_digest_sent_at: datetime | None


class DashboardSummaryOut(BaseModel):
    kpis: KpiSummaryOut
    alerts_by_day: list[AlertsByDayPointOut]
    top_stocks_30d: list[TopStockOut]
    recent_alerts: list[AlertOut]
    system_status: SystemStatusOut
