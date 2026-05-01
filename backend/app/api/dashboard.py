"""Single BFF endpoint that aggregates KPI + chart + top + feed + system status."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import ScanRun, User
from app.schemas.alert import AlertOut, ScanStatusOut
from app.schemas.dashboard import (
    AlertsByDayPointOut,
    DashboardSummaryOut,
    KpiSummaryOut,
    SystemStatusOut,
    TopStockOut,
)
from app.services import alert_service, stats_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _latest_scan(db: Session) -> ScanStatusOut | None:
    latest = (
        db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
        .scalar_one_or_none()
    )
    if latest is None:
        return None
    return ScanStatusOut(
        is_running=latest.status == "running",
        last_run_id=latest.id,
        trigger=latest.trigger,
        status=latest.status,
        phase=latest.phase,
        started_at=latest.started_at,
        completed_at=latest.completed_at,
        progress_done=latest.progress_done,
        progress_total=latest.progress_total,
        stocks_scanned=latest.stocks_scanned,
        stocks_skipped=latest.stocks_skipped,
        alerts_fired=latest.alerts_fired,
        error_message=latest.error_message,
    )


@router.get("/summary", response_model=DashboardSummaryOut)
def get_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardSummaryOut:
    kpi = stats_service.get_kpi_summary(db)
    by_day = stats_service.get_alerts_by_day(db, days=30)
    top = stats_service.get_top_stocks(db, days=30, limit=10)
    sys_status = stats_service.get_system_status(db)
    last_scan = _latest_scan(db)
    recent_items, _, _ = alert_service.list_alerts(db, limit=10, offset=0, archived=False)

    return DashboardSummaryOut(
        kpis=KpiSummaryOut(
            alerts_last_24h=kpi.alerts_last_24h,
            alerts_prev_24h=kpi.alerts_prev_24h,
            alerts_unread=kpi.alerts_unread,
            stocks_monitored=kpi.stocks_monitored,
            indices_count=kpi.indices_count,
            last_scan=last_scan,
            next_scan_at=sys_status.scan_alerts_next_run,
            next_digest_at=sys_status.send_digest_next_run,
        ),
        alerts_by_day=[
            AlertsByDayPointOut(date=p.date, count=p.count, by_kind=p.by_kind)
            for p in by_day
        ],
        top_stocks_30d=[
            TopStockOut(
                stock_id=t.stock_id,
                ticker=t.ticker,
                alert_count=t.alert_count,
                top_kind=t.top_kind,
            )
            for t in top
        ],
        recent_alerts=[AlertOut(**i) for i in recent_items],
        system_status=SystemStatusOut(
            scheduler_running=sys_status.scheduler_running,
            scan_alerts_next_run=sys_status.scan_alerts_next_run,
            send_digest_next_run=sys_status.send_digest_next_run,
            refresh_catalog_next_run=sys_status.refresh_catalog_next_run,
            telegram_configured=sys_status.telegram_configured,
            last_digest_sent_at=sys_status.last_digest_sent_at,
        ),
    )
