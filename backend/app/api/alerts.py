"""Alerts API: list/patch/bulk/export/scan/send-digest."""
import csv
import io
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.db import SessionLocal
from app.core.errors import UpstreamError
from app.models import Alert, ScanRun, Stock, User
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
    StockSignalScanOut,
)
from app.schemas.confluence import ConfluenceOut
from app.services import alert_service, confluence_service
from app.services.notifier_service import send_daily_digest
from app.services.ohlcv_service import fetch_and_upsert
from app.services.scan_runner import run_tracked_scan

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _run_scan_in_background(stock_ids: list[int] | None) -> None:
    """Manual scan entry. Single-scan guard FIRST: skip (no ScanRun row created)
    if a scan is already running, so we never start a 2nd concurrent SQLite
    writer ('database is locked'); otherwise run it holding the slot."""
    from app.services import scan_lock

    with scan_lock.scan_slot() as acquired:
        if not acquired:
            logger.info("[scan] manual scan skipped — another scan already running")
            return
        _run_scan_in_background_locked(stock_ids)


def _run_scan_in_background_locked(stock_ids: list[int] | None) -> None:
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
    from datetime import date

    from app.services import scan_cancel
    from app.services.ohlcv_fetch_plan import (
        KIND_SKIP,
        build_fetch_plan,
        iter_fetch_chunks,
    )
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
            # Per-stock baseline rates (sec/stock) used by the interpolator
            # to estimate how long each batch should take, so the bar moves
            # at the right pace. Slightly conservative — if the real fetch
            # finishes faster than the estimate, the main thread snaps the
            # final value forward; if slower, the interpolator caps at 95%
            # of the gap so we never overshoot the true count.
            SEC_PER_STOCK = {
                "incremental": 0.2,  # ~5/sec on warm cache
                "backfill": 1.0,     # ~1/sec for 10y of bars
            }

            # Sub-phase 0b: bulk staleness check. Single GROUP BY query —
            # cheap, but announced explicitly so the user knows what's
            # happening before the chunk loop's first tick.
            run.phase = "fetching:checking_staleness"
            run.current_target = (
                f"Verifica freschezza barre per {len(stocks)} stock…"
            )
            run.progress_done = 60
            db.commit()
            # Shared planning (ohlcv_fetch_plan, same planner as the cron
            # job): one bulk staleness GROUP BY, per-stock incremental/
            # backfill split on the 30-day cutoff, zero-bar dead-ticker
            # quarantine, staleness sort so each incremental chunk's
            # start=min(latest) window is tight for every member.
            plan = build_fetch_plan(db, stocks)
            if plan.quarantined:
                logger.info(
                    f"[scan] {len(plan.quarantined)} quarantined tickers skipped "
                    f"(weekly re-probe): {[s.ticker for s in plan.quarantined[:5]]}"
                )
            # Surface the incremental/backfill split in the toast so the user
            # knows whether the chunk loop is mostly the cheap incremental
            # path or the slow backfill path before the first chunk commits.
            need_backfill_n = len(plan.backfill)
            need_incremental_n = len(plan.incremental)
            # Surface "what's the freshest bar we have" so the user knows
            # the baseline before the chunk loop starts. max() across the
            # incremental population tells them "we already have data up
            # to <date>"; the gap to today is roughly how many new bars
            # the smart-incremental path will pull.
            inc_latest_dates = [plan.latest_dates[s.id] for s in plan.incremental]
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
            run.progress_total = plan.total
            run.progress_done = 0
            db.commit()

            # The chunk semantics — homogeneous incremental-then-backfill
            # chunks (one stale stock never drags fresh stocks down the 10y
            # path), overlap-by-one-session start=min(latest), smart-skip of
            # all-up-to-date chunks — live in iter_fetch_chunks (shared with
            # the cron job). This loop keeps only the manual-scan UI wiring:
            # progress_pulse interpolation, phase/target labels, cooperative
            # cancel, per-chunk commit.
            cursor = 0
            for chunk, kind, sub_start, sub_period in iter_fetch_chunks(
                plan, chunk_size
            ):
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
                end_done = cursor + len(chunk)
                if kind == KIND_SKIP:
                    # Every stock in the chunk already has TODAY's (settled)
                    # bar: nothing new AND nothing to revalidate. Advance the
                    # cursor + heartbeat without calling yfinance, so the bar
                    # still progresses honestly.
                    run.progress_done = end_done
                    bump_heartbeat(db, run)
                    cursor = end_done
                    continue

                run.phase = f"fetching:{kind}"
                tail = len(chunk) - 1
                run.current_target = (
                    chunk[0].ticker if tail == 0
                    else f"{chunk[0].ticker} +{tail}"
                )
                db.commit()

                expected_sec = max(0.5, len(chunk) * SEC_PER_STOCK[kind])
                try:
                    with progress_pulse(
                        run.id,
                        start_done=cursor,
                        end_done=end_done,
                        expected_duration_sec=expected_sec,
                    ):
                        if sub_start is not None:
                            fetch_and_upsert(db, chunk, start=sub_start)
                        else:
                            fetch_and_upsert(db, chunk, period=sub_period)
                    db.commit()
                except UpstreamError as e:
                    logger.warning(
                        f"[scan] upstream {e.source}.{e.op} failed: {e}"
                    )
                    db.rollback()
                    # continue — next chunk
                except Exception as e:  # noqa: BLE001 — defensive last-resort
                    logger.exception(f"[scan] unexpected error in fetch chunk: {e}")
                    db.rollback()
                    # continue — next chunk
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



_VALID_TONES = frozenset({"bull", "bear"})


def _validate_signal_filters(
    *,
    tone: str | None,
    strength_min: float | None,
    probability_min: float | None,
    nature: str | None,
    outcome: str | None = None,
    horizon: str | None = None,
) -> None:
    """Shared 422 validation for the snapshot-derived filters. Used by both
    the list endpoint and the CSV export so the two accept the exact same
    query surface (the export used to silently ignore these params — the
    2026-07-08 audit bug: filtered page, unfiltered CSV)."""
    if tone is not None and tone not in _VALID_TONES:
        raise HTTPException(
            status_code=422,
            detail=f"tone must be one of {sorted(_VALID_TONES)}, got: {tone!r}",
        )
    if strength_min is not None and not (0.0 <= strength_min <= 100.0):
        raise HTTPException(status_code=422, detail="strength_min must be in [0, 100]")
    if probability_min is not None and not (0.0 <= probability_min <= 100.0):
        raise HTTPException(status_code=422, detail="probability_min must be in [0, 100]")
    if nature is not None and nature not in ("continuazione", "inversione"):
        raise HTTPException(
            status_code=422,
            detail="nature must be 'continuazione' or 'inversione'",
        )
    # Realised-outcome + horizon filters (list endpoint only; defaults keep the
    # export call sites unchanged).
    if outcome is not None and outcome not in ("hit", "miss", "pending"):
        raise HTTPException(
            status_code=422,
            detail="outcome must be one of 'hit', 'miss', 'pending'",
        )
    if horizon is not None and horizon not in ("short", "medium", "long"):
        raise HTTPException(
            status_code=422,
            detail="horizon must be one of 'short', 'medium', 'long'",
        )


@router.get("", response_model=AlertListOut)
def list_alerts(
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
    outcome: str | None = None,
    horizon: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "triggered_at",
    sort_dir: str = "desc",
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlertListOut:
    from app.services.alert_service import _SORTABLE_KEYS

    if sort_dir not in ("asc", "desc"):
        raise HTTPException(
            status_code=422,
            detail=f"sort_dir must be 'asc' or 'desc', got: {sort_dir!r}",
        )
    if sort_by not in _SORTABLE_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"sort_by must be one of {sorted(_SORTABLE_KEYS)}, got: {sort_by!r}",
        )
    _validate_signal_filters(
        tone=tone,
        strength_min=strength_min,
        probability_min=probability_min,
        nature=nature,
        outcome=outcome,
        horizon=horizon,
    )
    if confidence_min is not None and not (0.0 <= confidence_min <= 100.0):
        raise HTTPException(
            status_code=422,
            detail="confidence_min must be in [0, 100]",
        )
    items, total, has_more = alert_service.list_alerts(
        db,
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
        outcome=outcome,
        horizon=horizon,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return AlertListOut(
        items=[AlertOut(**i) for i in items],
        total=total,
        has_more=has_more,
    )


@router.get("/confluence", response_model=list[ConfluenceOut])
def get_confluence(
    days: int = 7,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ConfluenceOut]:
    """Cluster currently-active signal alerts by ticker+direction and score the
    agreement (confluence). Read-time aggregation over existing alerts - the
    individual signals are untouched. `days` = active-window length (1-30)."""
    window = max(1, min(days, 30))
    clusters = confluence_service.compute_confluence(db, days=window)
    return [ConfluenceOut.model_validate(c) for c in clusters]


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


@router.get("/signal-calibration")
def signal_calibration(_user: User = Depends(get_current_user)) -> dict:
    """Per-detector calibration facts for the UI: base_rate (absolute hit),
    skill (market-neutral hit — beta-stripped), edge_pct, sample n, horizon, and
    an honesty `tag` (coinflip / negative / edge).

    Detector-LEVEL (identical for every alert of a detector), so it's served as
    a lookup — always reflects the current artifact, no per-alert storage and no
    backfill. The signal-detail UI joins on the alert's signal_name to show the
    skill view + honesty marker next to Probabilità.
    """
    from app.signals.calibration_map import get_calibration

    cal = get_calibration()
    return {"version": cal.version, "detectors": cal.all_detector_stats()}


@router.post("/scan/stop", response_model=ScanStopResult, dependencies=[Depends(require_json)])
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


# Hard cap on exported rows: the service pages at most 500 rows per query,
# so the export loops pages up to this bound. Generous enough for any real
# filtered working set; prevents an unbounded-memory CSV on "export all".
_EXPORT_MAX_ROWS = 10_000


def _snapshot_dict(raw: object) -> dict:
    """Best-effort parse of Alert.snapshot (Text column → JSON dict).
    Malformed/legacy payloads degrade to {} instead of breaking the export."""
    import json

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


@router.get("/export.csv")
def export_csv(
    ticker: str | None = None,
    q: str | None = None,
    rule_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: bool | None = False,
    tone: str | None = None,
    strength_min: float | None = None,
    probability_min: float | None = None,
    nature: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export the alerts matching the CURRENT filters as CSV.

    Accepts the same filter surface as the list endpoint (q / tone /
    strength_min / probability_min / nature included — the page sends them
    all), so what the user sees filtered is exactly what lands in the file.
    Columns follow the two-score model: signal_date + tone + strength +
    probability + realised outcome; the dead read_at axis was dropped.
    """
    _validate_signal_filters(
        tone=tone,
        strength_min=strength_min,
        probability_min=probability_min,
        nature=nature,
    )
    # The service clamps limit to 500 per call — page through until exhausted
    # (or the safety cap) so the export really covers every matching row.
    items: list[dict] = []
    offset = 0
    while len(items) < _EXPORT_MAX_ROWS:
        page, _, has_more = alert_service.list_alerts(
            db,
            ticker=ticker,
            q=q,
            rule_kind=rule_kind,
            date_from=date_from,
            date_to=date_to,
            archived=archived,
            tone=tone,
            strength_min=strength_min,
            probability_min=probability_min,
            nature=nature,
            limit=500,
            offset=offset,
        )
        items.extend(page)
        if not has_more:
            break
        offset += len(page)
    items = items[:_EXPORT_MAX_ROWS]

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "triggered_at",
            "signal_date",
            "ticker",
            "rule_kind",
            "trigger_price",
            "tone",
            "strength",
            "probability",
            "outcome_hit",
            "outcome_fwd_return",
            "outcome_horizon_days",
            "outcome_mkt_excess",
            "archived_at",
        ]
    )
    for it in items:
        snap = _snapshot_dict(it["snapshot"])
        # Forza: prefer the new `strength`, fall back to the transitional
        # `confidence` alias — same COALESCE the sort/filter paths use.
        strength = snap.get("strength", snap.get("confidence"))
        w.writerow(
            [
                it["id"],
                it["triggered_at"].isoformat() if it["triggered_at"] else "",
                it["signal_date"].isoformat() if it["signal_date"] else "",
                it["ticker"],
                it["rule_kind"],
                it["trigger_price"],
                snap.get("tone") or "",
                strength if strength is not None else "",
                snap.get("probability") if snap.get("probability") is not None else "",
                # Realised outcome (empty while maturing / for legacy rows).
                "" if it["outcome_hit"] is None else int(it["outcome_hit"]),
                it["outcome_fwd_return"] if it["outcome_fwd_return"] is not None else "",
                it["outcome_horizon_days"] if it["outcome_horizon_days"] is not None else "",
                it["outcome_mkt_excess"] if it["outcome_mkt_excess"] is not None else "",
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
    a = alert_service.patch_alert(db, alert_id, archived=payload.archived)
    if a is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    # Resolve ticker + rule_kind for AlertOut
    from app.models import Stock as _Stock
    rule_kind = alert_service.derive_rule_kind(None, a.signal_name)
    stock_row = db.execute(
        select(_Stock.ticker, _Stock.name).where(_Stock.id == a.stock_id)
    ).first()
    ticker = stock_row.ticker if stock_row else None
    name = stock_row.name if stock_row else None
    return AlertOut(
        id=a.id,
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
    # Best-effort pre-check: if a scan already holds the slot (cron, boot
    # catch-up, or another manual trigger), `_run_scan_in_background` would
    # just skip silently — the click would look "accepted" but do nothing.
    # Report that upfront so the frontend doesn't show a false "scan avviato"
    # toast (see the 2026-07-01 investigation: a boot catch-up scan running
    # is invisible to the caller, and the optimistic UI misreads the skip as
    # an instant completion of the user's own click).
    from app.services import scan_lock

    if scan_lock.is_running():
        return ScanAccepted(accepted=False)
    background.add_task(_run_scan_in_background, payload.stock_ids)
    return ScanAccepted(accepted=True)


@router.post(
    "/scan-stock/{ticker}",
    response_model=StockSignalScanOut,
    dependencies=[Depends(require_json)],
)
def scan_stock_signals(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockSignalScanOut:
    """Synchronously run the signal engine for ONE stock using its stored
    OHLCV (no network) and persist any new signal alerts. Powers the per-stock
    "processa segnali" button on the stock-detail signals card — the user gets
    immediate feedback instead of waiting for the next universe scan.

    Returns the count of newly-created alerts + the stock's current active
    signal-alert total. The detail page invalidates its query on success so the
    "Segnali storici" table reflects the new rows.
    """
    # Lazy imports: the scan helpers pull in pandas + the detector registry,
    # which we don't want at module import time for the lightweight alerts API.
    from app.services.scan_service import _load_ohlcv
    from app.signals.signal_scan_service import evaluate_signals

    # Catalog has duplicate ticker rows (CLAUDE.md) — pick any.
    stock = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")

    ohlcv = _load_ohlcv(db, stock.id)
    if ohlcv is None or len(ohlcv) < 2:
        raise HTTPException(
            status_code=422,
            detail="Storico prezzi insufficiente per processare i segnali",
        )
    added = evaluate_signals(db, stock, ohlcv)
    db.commit()
    total = db.execute(
        select(func.count())
        .select_from(Alert)
        .where(Alert.stock_id == stock.id, Alert.archived_at.is_(None))
    ).scalar() or 0
    return StockSignalScanOut(added=added, total=int(total))


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
