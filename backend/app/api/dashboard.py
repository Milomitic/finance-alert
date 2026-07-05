"""Single BFF endpoint that aggregates KPI + chart + top + feed + system status."""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.db import SessionLocal
from app.models import OhlcvDaily, ScanRun, Stock, User
from app.schemas.alert import AlertOut, ScanStatusOut
from app.schemas.dashboard import (
    AlertsByDayPointOut,
    AlertsByIndexPointOut,
    AnalystActionOut,
    DashboardSummaryOut,
    KpiSummaryOut,
    PremarketMoversOut,
    SystemStatusOut,
    TopStockOut,
)
from app.services import (
    alert_service,
    analyst_actions_feed,
    premarket_service,
    stats_service,
)

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
        current_target=latest.current_target,
        error_message=latest.error_message,
    )


@router.get("/analyst-actions", response_model=list[AnalystActionOut])
def get_analyst_actions(
    limit: int = 40,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[AnalystActionOut]:
    """Recent analyst upgrades/downgrades/initiations across the pool,
    newest first. Aggregated from the in-memory L1 fundamentals cache
    (see `analyst_actions_feed`), then enriched with company names via a
    single batched query against the Stock table."""
    # Filter to genuine rating CHANGES (up/down/init) on the backend so the
    # `limit` bounds the changes stream - not the Maintain-dominated raw feed.
    # (The frontend also filters, but that ran AFTER the limit, leaving only a
    # couple of changes when 40 maintains crowded the window.)
    items = analyst_actions_feed.recent_actions(
        limit=max(1, min(limit, 100)),
        actions=analyst_actions_feed.CHANGE_ACTIONS,
    )
    if not items:
        return []
    # Batch-resolve ticker → name in one query instead of N.
    tickers = {it.ticker for it in items}
    name_map = dict(
        db.execute(
            select(Stock.ticker, Stock.name).where(Stock.ticker.in_(tickers))
        ).all()
    )
    # Batch-resolve ticker → latest stored close (for the target's implied
    # upside vs current price). One correlated query for the ~N involved
    # tickers — each stock's most-recent ohlcv_daily bar.
    price_map = {
        t: float(c)
        for t, c in db.execute(
            select(Stock.ticker, OhlcvDaily.close)
            .join(OhlcvDaily, OhlcvDaily.stock_id == Stock.id)
            .where(
                Stock.ticker.in_(tickers),
                OhlcvDaily.date == (
                    select(func.max(OhlcvDaily.date))
                    .where(OhlcvDaily.stock_id == Stock.id)
                    .correlate(Stock)   # correlate ONLY the outer Stock, keep
                    .scalar_subquery()  # OhlcvDaily in the subquery's FROM
                ),
            )
        ).all()
        if c is not None
    }
    return [
        AnalystActionOut(
            ticker=it.ticker,
            name=name_map.get(it.ticker) or it.ticker,
            date=it.date,
            firm=it.firm,
            to_grade=it.to_grade,
            from_grade=it.from_grade,
            action=it.action,
            current_price_target=it.current_price_target,
            prior_price_target=it.prior_price_target,
            price_target_action=it.price_target_action,
            from_news=it.from_news,
            current_price=price_map.get(it.ticker),
        )
        for it in items
    ]


@router.get("/premarket-movers", response_model=PremarketMoversOut)
def get_premarket_movers(
    _user: User = Depends(get_current_user),
) -> PremarketMoversOut:
    """US pre-market top gainers/losers (cached by the scheduler job
    during the pre-market window). `available` is False — and the
    frontend hides the card — whenever the US regular market is open or
    the cached pre-market data is stale/empty."""
    s = premarket_service.get_state()
    return PremarketMoversOut(
        available=s["available"],
        market_open=s["market_open"],
        as_of=s.get("as_of"),
        computed_at=s.get("computed_at"),
        refreshing=s.get("refreshing", False),
        progress_pct=s.get("progress_pct", 0),
        gainers=s.get("gainers", []),
        losers=s.get("losers", []),
    )


def _premarket_refresh_task() -> None:
    db = SessionLocal()
    try:
        premarket_service.refresh(db)
    finally:
        db.close()


@router.post(
    "/premarket-movers/refresh", status_code=202, dependencies=[Depends(require_json)]
)
def refresh_premarket_movers(
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """On-demand recompute (the card's manual refresh button). Returns
    202 immediately; progress is polled via GET /premarket-movers
    (`refreshing` + `progress_pct`). De-duped: if a refresh is already
    in flight the in-flight one keeps running and this is a no-op."""
    state = premarket_service.get_state()
    if not state.get("refreshing"):
        background.add_task(_premarket_refresh_task)
    return {"accepted": True}


@router.get("/summary", response_model=DashboardSummaryOut)
def get_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardSummaryOut:
    kpi = stats_service.get_kpi_summary(db)
    by_day = stats_service.get_alerts_by_day(db, days=30)
    top = stats_service.get_top_stocks(db, days=30, limit=10)
    by_index = stats_service.get_alerts_by_index(db, days=30)
    sys_status = stats_service.get_system_status(db)
    last_scan = _latest_scan(db)
    recent_items, _, _ = alert_service.list_alerts(db, limit=10, offset=0, archived=False)

    return DashboardSummaryOut(
        kpis=KpiSummaryOut(
            alerts_last_24h=kpi.alerts_last_24h,
            alerts_prev_24h=kpi.alerts_prev_24h,
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
        alerts_by_index_30d=[
            AlertsByIndexPointOut(
                index_code=p.index_code,
                index_name=p.index_name,
                alert_count=p.alert_count,
            )
            for p in by_index
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
