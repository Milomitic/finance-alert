"""Alerts API: list/patch/bulk/unread-count/export/scan/send-digest."""
import csv
import io
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.db import SessionLocal
from app.models import ScanRun, Stock, User
from app.schemas.alert import (
    AlertListOut,
    AlertOut,
    AlertPatch,
    BulkAction,
    BulkResult,
    DigestResultOut,
    ScanAccepted,
    ScanRequest,
    ScanStatusOut,
    UnreadCountOut,
)
from app.services import alert_service
from app.services.notifier_service import send_daily_digest
from app.services.ohlcv_service import fetch_and_upsert
from app.services.scan_runner import run_tracked_scan

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _run_scan_in_background(stock_ids: list[int] | None) -> None:
    """Manual-trigger scan: track via ScanRun (fetch then evaluate phases).

    Creates the ScanRun row upfront with phase="fetching" so the UI's
    scan-status polling immediately shows "Scaricamento dati di mercato in corso"
    instead of an opaque silence during the (potentially long) yfinance backfill.
    Switches phase to "evaluating" before running the rules.
    """
    from datetime import date, timedelta

    from app.services.ohlcv_service import latest_ohlcv_date
    from app.services.scan_runner import create_scan_run, update_phase

    db = SessionLocal()
    try:
        if stock_ids:
            stocks = list(db.execute(select(Stock).where(Stock.id.in_(stock_ids))).scalars().all())
        else:
            stocks = list(db.execute(select(Stock)).scalars().all())

        # Phase 1: fetch — create the ScanRun row so the UI shows progress.
        run = create_scan_run(db, trigger="manual", phase="fetching")
        run.progress_total = len(stocks)
        db.commit()

        if stocks:
            chunk_size = 100
            cutoff = date.today() - timedelta(days=30)
            for i in range(0, len(stocks), chunk_size):
                chunk = stocks[i : i + chunk_size]
                needs_backfill = any(
                    latest_ohlcv_date(db, s.id) is None or latest_ohlcv_date(db, s.id) < cutoff
                    for s in chunk
                )
                period = "1y" if needs_backfill else "1mo"
                try:
                    fetch_and_upsert(db, chunk, period=period)
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
                    # continue with the next chunk
                # Surface fetch progress via progress_done
                run.progress_done = min(i + chunk_size, len(stocks))
                db.commit()

        # Phase 2: evaluate (reuse the same row; run_tracked_scan switches phase)
        update_phase(db, run, "evaluating")
        # Reset the progress counter for the evaluation phase
        run.progress_done = 0
        db.commit()
        run_tracked_scan(db, trigger="manual", existing_run=run)
    finally:
        db.close()



@router.get("", response_model=AlertListOut)
def list_alerts(
    ticker: str | None = None,
    rule_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    read: bool | None = None,
    archived: bool | None = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlertListOut:
    items, total, has_more = alert_service.list_alerts(
        db,
        ticker=ticker,
        rule_kind=rule_kind,
        date_from=date_from,
        date_to=date_to,
        read=read,
        archived=archived,
        limit=limit,
        offset=offset,
    )
    return AlertListOut(
        items=[AlertOut(**i) for i in items],
        total=total,
        has_more=has_more,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def get_unread_count(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> UnreadCountOut:
    return UnreadCountOut(count=alert_service.unread_count(db))


@router.get("/scan-status", response_model=ScanStatusOut)
def scan_status(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> ScanStatusOut:
    """Return the most recent ScanRun (or empty if no scan has ever run).

    Used by the UI to render the live scan progress card and to know when to
    invalidate the alerts list (after a scan transitions running -> success).
    """
    latest = (
        db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
        .scalar_one_or_none()
    )
    if latest is None:
        return ScanStatusOut(is_running=False)
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


@router.get("/export.csv")
def export_csv(
    ticker: str | None = None,
    rule_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    read: bool | None = None,
    archived: bool | None = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StreamingResponse:
    items, _, _ = alert_service.list_alerts(
        db,
        ticker=ticker,
        rule_kind=rule_kind,
        date_from=date_from,
        date_to=date_to,
        read=read,
        archived=archived,
        limit=10000,
        offset=0,
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["id", "triggered_at", "ticker", "rule_kind", "trigger_price", "read_at", "archived_at"]
    )
    for it in items:
        w.writerow(
            [
                it["id"],
                it["triggered_at"].isoformat() if it["triggered_at"] else "",
                it["ticker"],
                it["rule_kind"],
                it["trigger_price"],
                it["read_at"].isoformat() if it["read_at"] else "",
                it["archived_at"].isoformat() if it["archived_at"] else "",
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alerts.csv"},
    )


@router.patch("/{alert_id}", response_model=AlertOut, dependencies=[Depends(require_json)])
def patch(
    alert_id: int,
    payload: AlertPatch,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlertOut:
    a = alert_service.patch_alert(db, alert_id, read=payload.read, archived=payload.archived)
    if a is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    # Resolve ticker + rule_kind for AlertOut
    from app.models import Rule as _Rule
    from app.models import Stock as _Stock
    rule_kind = db.execute(select(_Rule.kind).where(_Rule.id == a.rule_id)).scalar_one_or_none()
    ticker = db.execute(select(_Stock.ticker).where(_Stock.id == a.stock_id)).scalar_one_or_none()
    return AlertOut(
        id=a.id,
        rule_id=a.rule_id,
        rule_kind=rule_kind,
        stock_id=a.stock_id,
        ticker=ticker,
        triggered_at=a.triggered_at,
        trigger_price=float(a.trigger_price),
        snapshot=a.snapshot,
        read_at=a.read_at,
        archived_at=a.archived_at,
    )


@router.post("/bulk", response_model=BulkResult, dependencies=[Depends(require_json)])
def bulk(
    payload: BulkAction,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BulkResult:
    affected = alert_service.bulk_action(db, payload.ids, payload.action)
    return BulkResult(affected=affected)


@router.post(
    "/scan",
    response_model=ScanAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_json)],
)
def trigger_scan(
    payload: ScanRequest,
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
) -> ScanAccepted:
    background.add_task(_run_scan_in_background, payload.stock_ids)
    return ScanAccepted(accepted=True)


@router.post(
    "/send-digest", response_model=DigestResultOut, dependencies=[Depends(require_json)]
)
def trigger_digest(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DigestResultOut:
    result = send_daily_digest(db)
    return DigestResultOut(
        sent=result.sent, alerts_count=result.alerts_count, reason=result.reason
    )
