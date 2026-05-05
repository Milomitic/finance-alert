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
    ScanStopResult,
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

    from app.services import scan_cancel
    from app.services.ohlcv_service import latest_ohlcv_date
    from app.services.scan_runner import bump_heartbeat, create_scan_run, update_phase

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
                # Cooperative cancel during fetch phase too — the fetch can take
                # several minutes for a fresh DB and the user shouldn't have to
                # wait for evaluate to start before being able to stop the scan.
                if scan_cancel.is_cancel_requested(run.id):
                    from datetime import datetime, UTC
                    run.status = "failed"
                    run.phase = None
                    run.error_message = "Cancellato dall'utente"
                    run.completed_at = datetime.now(UTC)
                    db.commit()
                    scan_cancel.clear(run.id)
                    return
                chunk = stocks[i : i + chunk_size]
                needs_backfill = any(
                    latest_ohlcv_date(db, s.id) is None or latest_ohlcv_date(db, s.id) < cutoff
                    for s in chunk
                )
                # Initial backfill grabs 10 years of bars so the new 5Y chart
                # range works out of the box and historical-analysis surfaces
                # (5Y view + long-window indicators like SMA200) have enough
                # data to compute. Incremental scans keep the cheap "1mo"
                # fetch — they only need the last few bars for evaluation.
                period = "10y" if needs_backfill else "1mo"
                try:
                    fetch_and_upsert(db, chunk, period=period)
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
                    # continue with the next chunk
                # Surface fetch progress via progress_done + bump heartbeat
                run.progress_done = min(i + chunk_size, len(stocks))
                bump_heartbeat(db, run)

        # Phase 2: evaluate (reuse the same row; run_tracked_scan switches phase)
        update_phase(db, run, "evaluating")
        # Reset the progress counter for the evaluation phase
        run.progress_done = 0
        bump_heartbeat(db, run)
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


# A scan is considered "stale" (worker likely dead) if no heartbeat for this
# many seconds. Tuned to 120s = 2× the worst-case time between fetch chunks
# (a slow yfinance call) — anything longer almost certainly means the worker
# died, not that it's just chewing on a particularly slow chunk.
SCAN_STALE_THRESHOLD_SEC = 120


def _build_scan_status(latest: ScanRun) -> ScanStatusOut:
    """Helper that derives stale/seconds-since-heartbeat from a ScanRun row."""
    from datetime import datetime, UTC

    is_running = latest.status == "running"
    seconds_since_progress: int | None = None
    is_stale = False
    if is_running:
        ref = latest.last_progress_at or latest.started_at
        if ref is not None:
            # SQLite returns naive datetimes — coerce to UTC for the diff to work
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=UTC)
            seconds_since_progress = int((datetime.now(UTC) - ref).total_seconds())
            is_stale = seconds_since_progress > SCAN_STALE_THRESHOLD_SEC
    return ScanStatusOut(
        is_running=is_running,
        last_run_id=latest.id,
        trigger=latest.trigger,
        status=latest.status,
        phase=latest.phase,
        started_at=latest.started_at,
        completed_at=latest.completed_at,
        last_progress_at=latest.last_progress_at,
        progress_done=latest.progress_done,
        progress_total=latest.progress_total,
        stocks_scanned=latest.stocks_scanned,
        stocks_skipped=latest.stocks_skipped,
        alerts_fired=latest.alerts_fired,
        error_message=latest.error_message,
        is_stale=is_stale,
        seconds_since_last_progress=seconds_since_progress,
    )


@router.get("/scan-status", response_model=ScanStatusOut)
def scan_status(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> ScanStatusOut:
    """Return the most recent ScanRun (or empty if no scan has ever run).

    Used by the UI to render the live scan progress card and to know when to
    invalidate the alerts list (after a scan transitions running -> success).
    Includes `is_stale=True` when the row says 'running' but no heartbeat for
    >2min — the UI uses that to surface a "Stuck — Stop" warning.
    """
    latest = (
        db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
        .scalar_one_or_none()
    )
    if latest is None:
        return ScanStatusOut(is_running=False)
    return _build_scan_status(latest)


@router.post("/scan/stop", response_model=ScanStopResult)
def stop_scan(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> ScanStopResult:
    """Stop the latest running scan.

    Two flavors:
    1. **Live worker**: registers a cancel request the scan loop polls between
       iterations. Within `progress_every` (~10) stocks the loop bails out and
       the runner marks the row as failed with "Cancellato dall'utente".
    2. **Orphan row** (stale heartbeat): the worker died. The cancel flag would
       never be checked, so we force-mark the row as failed inline here. The
       UI is unblocked immediately (no polling for the runner to bail).

    Idempotent: calling /stop when no scan is running returns
    `was_running=False` with an explanatory message.
    """
    from datetime import datetime, UTC

    from app.services import scan_cancel

    latest = (
        db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
        .scalar_one_or_none()
    )
    if latest is None:
        return ScanStopResult(
            stopped_run_id=None,
            was_running=False,
            was_stale=False,
            message="Nessuno scan da fermare.",
        )
    if latest.status != "running":
        return ScanStopResult(
            stopped_run_id=latest.id,
            was_running=False,
            was_stale=False,
            message=f"Ultimo scan già in stato '{latest.status}'.",
        )

    # Compute stale-ness via the same helper used by /scan-status
    status = _build_scan_status(latest)
    is_stale = status.is_stale

    if is_stale:
        # Orphan: force-close inline. The cancel flag would never be checked.
        latest.status = "failed"
        latest.phase = None
        latest.error_message = (
            "Worker non risponde da oltre "
            f"{status.seconds_since_last_progress}s — chiusura forzata. "
            "Probabile crash del processo backend."
        )
        latest.completed_at = datetime.now(UTC)
        db.commit()
        # Also clear any pending cancel for this id (defensive, in case the
        # worker comes back from the dead — it'll see cleared flag and just
        # complete the success path against an already-failed row).
        scan_cancel.clear(latest.id)
        return ScanStopResult(
            stopped_run_id=latest.id,
            was_running=True,
            was_stale=True,
            message="Scan bloccato terminato (cleanup forzato).",
        )

    # Live worker: cooperative cancel. The runner will mark the row as failed
    # within one `progress_every` window (~10 stocks).
    scan_cancel.request_cancel(latest.id)
    return ScanStopResult(
        stopped_run_id=latest.id,
        was_running=True,
        was_stale=False,
        message="Cancellazione richiesta. Il worker si fermerà entro pochi secondi.",
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
    stock_row = db.execute(
        select(_Stock.ticker, _Stock.name).where(_Stock.id == a.stock_id)
    ).first()
    ticker = stock_row.ticker if stock_row else None
    name = stock_row.name if stock_row else None
    return AlertOut(
        id=a.id,
        rule_id=a.rule_id,
        rule_kind=rule_kind,
        stock_id=a.stock_id,
        ticker=ticker,
        name=name,
        triggered_at=a.triggered_at,
        signal_date=a.signal_date,
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
