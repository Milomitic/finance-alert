"""Alerts API: list/patch/bulk/unread-count/export/scan/send-digest."""
import csv
import io
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.db import SessionLocal
from app.core.errors import UpstreamError
from app.models import ScanRun, Stock, User
from app.models.scan_run import KIND_ALERTS_SCAN
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
    """Manual-trigger scan: track via ScanRun with sub-phased fetch + evaluate.

    Phase taxonomy (colon-delimited so existing frontend parsing extends
    naturally; the prefix before `:` keeps the broad-stroke meaning):

      fetching:loading_catalog    — SELECT the universe of stocks
      fetching:checking_staleness — single bulk GROUP BY to compute, per
                                     stock, the latest OHLCV bar date
                                     (drives the backfill-vs-incremental
                                     decision per chunk)
      fetching:backfill           — chunk loop with period="10y" (slow path:
                                     stocks with no data or >30-day-stale)
      fetching:incremental        — chunk loop with period="1mo" (fast path:
                                     stocks with fresh data; usually 95%+
                                     of the universe on consecutive scans)
      evaluating:loading_rules    — between fetch end and the first
                                     scan_universe iteration; covers
                                     _load_global_rules + setup
      evaluating:scoring          — main per-stock rule-evaluation loop
      evaluating:market_snapshot  — refresh of breadth + leaders snapshot
      evaluating:scoring_recompute — sector_stats pre-pass + per-stock
                                     composite recompute
      evaluating:price_alerts     — price-target alert evaluation pass

    The two prep sub-phases (`fetching:loading_catalog`,
    `fetching:checking_staleness`) used to be lumped into one
    `fetching:planning` umbrella, but it flashed by too fast for the user
    to read; splitting + setting an explicit `current_target` lets the
    toast announce what the system is doing before the chunk counter
    starts moving. See May 2026 UX note in CLAUDE.md.

    The `current_target` column carries "what we're touching right now":
    a human-readable description during prep sub-phases, ticker of the
    first stock in the current chunk during fetch, ticker of the current
    stock during evaluate. The UI surfaces it as a small chip below the
    phase label.
    """
    from datetime import date, timedelta

    from app.services import scan_cancel
    from app.services.ohlcv_service import latest_ohlcv_dates_bulk
    from app.services.scan_runner import (
        bump_heartbeat,
        create_scan_run,
        progress_pulse,
        update_phase,
    )

    db = SessionLocal()
    try:
        # Sub-phase 0a: announce "loading universe" BEFORE the SELECT so the
        # toast shows that text even on a slow first DB query.
        #
        # Per-step atomic progress (May 2026 UX iteration): Step 1
        # (Preparazione catalogo) gets a synthetic 0-100 % bar instead of
        # the stock-count denominator. The two prep sub-phases — catalog
        # SELECT + bulk staleness GROUP BY — are sub-second each on warm
        # DB and have no per-row granularity, so a per-stock counter would
        # sit at 0/N for the whole step (the user complaint). Bar advances
        # in manual steps (40 → 60 → 100) at the natural sub-phase
        # boundaries; bar resets to the real stock count just before the
        # Step 2 download loop kicks in.
        run = create_scan_run(
            db, trigger="manual", phase="fetching:loading_catalog"
        )
        run.current_target = "Caricamento elenco stock dal catalogo…"
        run.progress_total = 100
        run.progress_done = 0
        db.commit()

        if stock_ids:
            stocks = list(db.execute(select(Stock).where(Stock.id.in_(stock_ids))).scalars().all())
        else:
            stocks = list(db.execute(select(Stock)).scalars().all())
        run.progress_done = 40
        run.current_target = f"{len(stocks)} stock caricati"
        db.commit()

        if stocks:
            # Fetch chunk size: 20 (was 100). Smaller batches give the user
            # more frequent honest progress updates AND keep yfinance's
            # internal HTTP overhead manageable (~5-10s of total added
            # overhead vs. the previous 100-batch pattern, on ~1100 stocks
            # — acceptable for the perceived-responsiveness gain). The
            # progress_pulse below interpolates progress_done within each
            # batch so the bar moves smoothly between boundaries.
            chunk_size = 20
            cutoff = date.today() - timedelta(days=30)
            # Per-stock baseline rates (sec/stock) used by the interpolator
            # to estimate how long each batch should take, so the bar moves
            # at the right pace. Slightly conservative — if the real fetch
            # finishes faster than the estimate, the main thread snaps the
            # final value forward; if slower, the interpolator caps at 95%
            # of the gap so we never overshoot the true count.
            INCREMENTAL_SEC_PER_STOCK = 0.2  # ~5/sec on warm cache
            BACKFILL_SEC_PER_STOCK = 1.0     # ~1/sec for 10y of bars

            # Sub-phase 0b: bulk staleness check. Single GROUP BY query —
            # cheap, but announced explicitly so the user knows what's
            # happening before the chunk loop's first tick.
            run.phase = "fetching:checking_staleness"
            run.current_target = (
                f"Verifica freschezza barre per {len(stocks)} stock…"
            )
            run.progress_done = 60
            db.commit()
            # B2 — one bulk SELECT replaces N×chunk_size point lookups. For
            # 1132 stocks × 12 chunks that was ~13k indexed queries; now it's
            # a single GROUP BY scan + in-memory dict reads.
            latest_dates = latest_ohlcv_dates_bulk(db, [s.id for s in stocks])
            # Count how many stocks fall on each side of the staleness cutoff
            # — surface it in the toast so the user knows whether the chunk
            # loop is mostly the cheap incremental path or the slow backfill
            # path before the first chunk even commits.
            need_backfill_n = sum(
                1
                for s in stocks
                if latest_dates.get(s.id) is None or latest_dates[s.id] < cutoff
            )
            need_incremental_n = len(stocks) - need_backfill_n
            # Surface "what's the freshest bar we have" so the user knows
            # the baseline before the chunk loop starts. max() across the
            # incremental population tells them "we already have data up
            # to <date>"; the gap to today is roughly how many new bars
            # the smart-incremental path will pull.
            inc_latest_dates = [
                latest_dates[s.id]
                for s in stocks
                if latest_dates.get(s.id) is not None
                and latest_dates[s.id] >= cutoff
            ]
            if inc_latest_dates:
                global_max = max(inc_latest_dates)
                gap_days = max(0, (date.today() - global_max).days)
                run.current_target = (
                    f"Dati al {global_max.strftime('%d %b').lower()} "
                    f"· {need_incremental_n} incrementali (~{gap_days}gg) "
                    f"· {need_backfill_n} backfill"
                )
            else:
                run.current_target = (
                    f"{need_incremental_n} incrementali · {need_backfill_n} backfill 10y"
                )
            # Step 1 (Preparazione) terminata: snap del bar a 100% prima
            # di passare al reset Step 2 (Download), così l'ultima frame
            # del passo precedente è visibile per un istante.
            run.progress_done = 100
            db.commit()
            bump_heartbeat(db, run)

            # Step 2 (Download dati di mercato) — reset del bar all'unità
            # atomica di questo passo: stock scaricati / N. Il chunk loop
            # qui sotto avanza progress_done per stock (cursor) e
            # progress_pulse interpola tra i confini dei chunk.
            run.progress_total = len(stocks)
            run.progress_done = 0
            db.commit()

            for i in range(0, len(stocks), chunk_size):
                # Cooperative cancel during fetch phase too — the fetch can take
                # several minutes for a fresh DB and the user shouldn't have to
                # wait for evaluate to start before being able to stop the scan.
                if scan_cancel.is_cancel_requested(run.id):
                    from datetime import datetime, UTC
                    run.status = "failed"
                    run.phase = None
                    run.current_target = None
                    run.error_message = "Cancellato dall'utente"
                    run.completed_at = datetime.now(UTC)
                    db.commit()
                    scan_cancel.clear(run.id)
                    return
                chunk = stocks[i : i + chunk_size]
                # SPLIT BY PERIOD — previously the entire chunk was sent
                # with `period="10y"` whenever even ONE stock in it needed
                # backfill, which forced yfinance to re-download 10 years
                # of bars for the (often ~19) other stocks in the chunk
                # that only needed "1mo". Big invisible cost on mixed
                # chunks. By splitting the chunk into two sub-batches and
                # making two yf.download calls with the right period for
                # each, fresh stocks never pay the backfill tax.
                #
                # The cost is one extra HTTP roundtrip per mixed chunk
                # (~150-300ms of yfinance overhead). Worth it: a single
                # over-fetched stock at 10y replays ~2520 bars × ~5ms of
                # UPSERT = ~12s. Recovering even one such stock per chunk
                # already pays for the extra roundtrip.
                incremental_chunk = [
                    s for s in chunk
                    if latest_dates.get(s.id) is not None
                    and latest_dates[s.id] >= cutoff
                ]
                backfill_chunk = [
                    s for s in chunk
                    if latest_dates.get(s.id) is None
                    or latest_dates[s.id] < cutoff
                ]

                # Run sub-batches in order: incremental first (faster,
                # gives the user immediate progress feedback), then
                # backfill (slower, dominates wall-time on mixed chunks).
                # The phase label flips per sub-batch so the toast
                # accurately announces which path is currently running.
                #
                # SMART-INCREMENTAL: instead of `period="1mo"` (which
                # re-downloads ~22 bars per stock and UPSERTs identical
                # rows), we pass `start=min(latest_date)+1` so yfinance
                # returns ONLY the bars after the oldest already-stored
                # date in the sub-batch. Stocks with newer latest_date
                # get a few extra bars too (UPSERT handles the dups
                # transparently) — accepting that minor over-fetch is
                # the price of keeping the batch as a single HTTP call.
                #
                # Edge case — `start > today`: every stock in the
                # sub-batch already has today's bar (or future). yfinance
                # would return an empty frame, which is wasted work. Guard
                # by skipping the call entirely in that case.
                cursor = i
                inc_start: date | None = None
                if incremental_chunk:
                    inc_start = min(
                        latest_dates[s.id] for s in incremental_chunk
                    ) + timedelta(days=1)

                for sub_chunk, sec_per_stock, phase_label, sub_start, sub_period in (
                    (incremental_chunk, INCREMENTAL_SEC_PER_STOCK, "fetching:incremental", inc_start, None),
                    (backfill_chunk,    BACKFILL_SEC_PER_STOCK,    "fetching:backfill",    None,      "10y"),
                ):
                    if not sub_chunk:
                        continue
                    # Smart skip — if the sub-batch's start date is in
                    # the future, every stock is already up to date.
                    # Advance the cursor + heartbeat without calling
                    # yfinance, so the bar still progresses honestly.
                    if sub_start is not None and sub_start > date.today():
                        end_done = cursor + len(sub_chunk)
                        run.progress_done = end_done
                        bump_heartbeat(db, run)
                        cursor = end_done
                        continue

                    run.phase = phase_label
                    tail = len(sub_chunk) - 1
                    run.current_target = (
                        sub_chunk[0].ticker if tail == 0
                        else f"{sub_chunk[0].ticker} +{tail}"
                    )
                    db.commit()

                    expected_sec = max(0.5, len(sub_chunk) * sec_per_stock)
                    end_done = cursor + len(sub_chunk)
                    try:
                        with progress_pulse(
                            run.id,
                            start_done=cursor,
                            end_done=end_done,
                            expected_duration_sec=expected_sec,
                        ):
                            if sub_start is not None:
                                fetch_and_upsert(db, sub_chunk, start=sub_start)
                            else:
                                fetch_and_upsert(db, sub_chunk, period=sub_period)
                        db.commit()
                    except UpstreamError as e:
                        logger.warning(
                            f"[scan] upstream {e.source}.{e.op} failed: {e}"
                        )
                        db.rollback()
                        # continue — next sub-batch / next chunk
                    except Exception as e:  # noqa: BLE001 — defensive last-resort
                        logger.exception(f"[scan] unexpected error in fetch chunk: {e}")
                        db.rollback()
                        # continue — next sub-batch / next chunk
                    run.progress_done = end_done
                    bump_heartbeat(db, run)
                    cursor = end_done

        # Phase 2: evaluate. Start in "loading_rules" — scan_universe flips
        # to "evaluating:scoring" on the first on_progress tick (done=0) so
        # the UI shows the rule-load sub-phase even when it's fast.
        update_phase(db, run, "evaluating:loading_rules")
        run.progress_done = 0
        run.current_target = None
        bump_heartbeat(db, run)
        run_tracked_scan(db, trigger="manual", existing_run=run)
    finally:
        db.close()



@router.get("", response_model=AlertListOut)
def list_alerts(
    ticker: str | None = None,
    q: str | None = None,
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
        q=q,
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
# Re-exported for backwards compatibility with anything that still imports
# them from this module (test_api_alerts.py, etc.). Source of truth lives
# in app.services.scan_status now.
from app.services.scan_status import SCAN_STALE_THRESHOLD_SEC, build_scan_status_out as _build_scan_status  # noqa: E402, F401


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
    # Filter by kind so the alert-scan toast doesn't pick up rows belonging
    # to score-recompute runs (they live in the same table since
    # 6ed5a4d41b17). See `app/api/scores.py:recompute_status` for the mirror.
    latest = (
        db.execute(
            select(ScanRun)
            .where(ScanRun.kind == KIND_ALERTS_SCAN)
            .order_by(ScanRun.started_at.desc())
            .limit(1)
        )
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

    # Filter by kind: stopping the latest "scan" must not accidentally
    # abort a concurrent score-recompute run. The mirror endpoint
    # /api/scores/recompute-stop owns the score_recompute side.
    latest = (
        db.execute(
            select(ScanRun)
            .where(ScanRun.kind == KIND_ALERTS_SCAN)
            .order_by(ScanRun.started_at.desc())
            .limit(1)
        )
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
    rule_kind = alert_service.derive_rule_kind(rule_kind, a.signal_name)
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
