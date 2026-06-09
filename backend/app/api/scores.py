"""Score API: per-stock score breakdown + cross-universe top picks.

Both endpoints require auth (consistent with the rest of /api). The single-
stock endpoint returns the persisted breakdown verbatim — the UI walks the
dict to render component bars without re-fetching upstream data.
"""
import json
from typing import Annotated, get_args

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.db import SessionLocal
from app.core.errors import UpstreamError
from app.core.visibility import visible_country_clause
from app.models import OhlcvDaily, ScanRun, Stock, StockScore, TechnicalScore, User
from app.models.scan_run import KIND_SCORE_RECOMPUTE
from app.schemas.alert import ScanAccepted, ScanStatusOut, ScanStopResult
from app.schemas.score import (
    RiskTier,
    ScoreCategory,
    StockScoreOut,
    SubScoresOut,
    TechnicalScoreOut,
    TopPickItemOut,
    TopPicksOut,
)
from app.services import (
    score_service,
    stock_fundamentals_service,
    technical_score_service,
)
from app.services.scan_status import build_scan_status_out

router = APIRouter(prefix="/api", tags=["scores"])


def _sector_avg_composite(db: Session, sector: str | None) -> float | None:
    """Average composite score across all scored stocks in `sector` — the
    gauge's 'media settore' reference marker. None when the sector is
    unknown/empty or has no scored peers."""
    if not sector:
        return None
    val = db.execute(
        select(func.avg(StockScore.composite))
        .select_from(StockScore)
        .join(Stock, Stock.id == StockScore.stock_id)
        .where(Stock.sector == sector)
    ).scalar()
    return round(float(val), 1) if val is not None else None


def _composite_percentiles(
    db: Session, sector: str | None, composite: float | None
) -> dict[str, int | None]:
    """Percentile rank (0-100, higher = better) of `composite` within the
    stock's SECTOR and the whole scored UNIVERSE, plus the sector peer count.
    Percentile = share of peers with composite <= this one. Cheap (counts over
    the indexed composite). Returns (sector_pct, universe_pct, peer_n); each
    None when there are no peers (or unknown sector)."""
    if composite is None:
        return {"sector_percentile": None, "universe_percentile": None, "peer_n": None}
    uni_total = db.execute(select(func.count()).select_from(StockScore)).scalar() or 0
    universe_pct: int | None = None
    if uni_total:
        uni_le = db.execute(
            select(func.count()).select_from(StockScore)
            .where(StockScore.composite <= composite)
        ).scalar() or 0
        universe_pct = round(100.0 * uni_le / uni_total)

    sector_pct: int | None = None
    peer_n: int | None = None
    if sector:
        peer_n = db.execute(
            select(func.count()).select_from(StockScore)
            .join(Stock, Stock.id == StockScore.stock_id)
            .where(Stock.sector == sector)
        ).scalar() or 0
        if peer_n:
            sec_le = db.execute(
                select(func.count()).select_from(StockScore)
                .join(Stock, Stock.id == StockScore.stock_id)
                .where(Stock.sector == sector, StockScore.composite <= composite)
            ).scalar() or 0
            sector_pct = round(100.0 * sec_le / peer_n)
    return {
        "sector_percentile": sector_pct,
        "universe_percentile": universe_pct,
        "peer_n": peer_n or None,
    }


_VALID_RISK = set(get_args(RiskTier))
_VALID_CATEGORY = set(get_args(ScoreCategory))

# A "top pick" must rest on enough real data. Scores whose QW5
# confidence/coverage (breakdown._meta_global.coverage) is below this
# — or unknown — are excluded from /scores/top so the homepage cards
# never surface a high number that's built on a thin factor base.
_MIN_CONFIDENCE = 0.70


@router.get("/stocks/{ticker}/score", response_model=StockScoreOut)
def get_stock_score(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockScoreOut:
    """Single-stock score + breakdown.

    Returns 404 if the ticker is unknown OR if no score has been computed yet
    for it (with the friendly "wait for next scan" message in the latter case).
    """
    # Catalog has duplicate ticker rows (CLAUDE.md) — pick any.
    stock = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")

    # Score might be on a different stock_id row if there are duplicates;
    # check both the chosen row's id AND any other duplicate.
    dup_ids = [
        sid for sid in db.execute(
            select(Stock.id).where(Stock.ticker == ticker)
        ).scalars().all()
    ]
    score = db.execute(
        select(StockScore).where(StockScore.stock_id.in_(dup_ids)).limit(1)
    ).scalars().first()
    if score is None:
        raise HTTPException(
            status_code=404,
            detail="Score not yet computed — wait for the next scan",
        )

    try:
        breakdown = json.loads(score.breakdown or "{}")
    except json.JSONDecodeError:
        breakdown = {}

    return StockScoreOut(
        stock_id=score.stock_id,
        ticker=stock.ticker,
        composite=score.composite,
        sub_scores=SubScoresOut(
            quality=score.quality,
            profitability=score.profitability,
            sustainability=score.sustainability,
            growth=score.growth,
            value=score.value,
            momentum=score.momentum,
            sentiment=score.sentiment,
        ),
        risk_tier=score.risk_tier,  # type: ignore[arg-type]
        computed_at=score.computed_at,
        breakdown=breakdown,
        sector_avg=_sector_avg_composite(db, stock.sector),
        **_composite_percentiles(db, stock.sector, score.composite),
    )


@router.get("/stocks/{ticker}/technical", response_model=TechnicalScoreOut)
def get_stock_technical(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TechnicalScoreOut:
    """Single-stock continuous technical score. 404 if the ticker is unknown or
    no technical score has been computed yet."""
    stock = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")
    dup_ids = [
        sid for sid in db.execute(
            select(Stock.id).where(Stock.ticker == ticker)
        ).scalars().all()
    ]
    ts = db.execute(
        select(TechnicalScore).where(TechnicalScore.stock_id.in_(dup_ids)).limit(1)
    ).scalars().first()
    if ts is None:
        raise HTTPException(
            status_code=404,
            detail="Technical score not yet computed (wait for the next scan)",
        )
    return TechnicalScoreOut(
        stock_id=ts.stock_id,
        ticker=stock.ticker,
        composite=ts.composite,
        trend=ts.trend,
        momentum=ts.momentum,
        structure=ts.structure,
        volume=ts.volume,
        rel_strength=ts.rel_strength,
        signals=ts.signals,
        posture=ts.posture,
        computed_at=ts.computed_at,
    )


@router.post("/stocks/{ticker}/technical/recompute", response_model=TechnicalScoreOut)
def recompute_stock_technical(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TechnicalScoreOut:
    """Force a single-stock technical-score recomputation from stored OHLCV and
    return the fresh row.

    Why this endpoint exists: the GET reads the persisted `technical_scores`
    row (last refreshed by the periodic scan's finalize pass). If a stock was
    skipped at scan time (too little history then, malformed bar, etc.) the row
    can be missing or stale. This is the per-card "refresh" escape hatch on the
    detail page. The cross-sectional relative-strength percentile is reused from
    the prior row (it needs the whole universe); the four price dimensions are
    recomputed from the latest stored bars.
    """
    stock = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")
    ts = technical_score_service.recompute_one(db, stock.id)
    if ts is None:
        raise HTTPException(
            status_code=422,
            detail="Storico prezzi insufficiente per calcolare lo score tecnico",
        )
    return TechnicalScoreOut(
        stock_id=ts.stock_id,
        ticker=stock.ticker,
        composite=ts.composite,
        trend=ts.trend,
        momentum=ts.momentum,
        structure=ts.structure,
        volume=ts.volume,
        rel_strength=ts.rel_strength,
        signals=ts.signals,
        posture=ts.posture,
        computed_at=ts.computed_at,
    )


@router.post("/stocks/{ticker}/score/recompute", response_model=StockScoreOut)
def recompute_stock_score(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockScoreOut:
    """Force a single-stock score recomputation, persist it, and return the
    fresh result.

    Why this endpoint exists: the GET endpoint reads the persisted score from
    `stock_scores` (last refreshed by the periodic `scan_runner` recompute_all
    pass). When fundamentals were partial at scan time (rate-limited yfinance
    `Ticker.info` failure), pillars derived entirely from `Ticker.info` —
    profitability and value — get persisted as None. Once the partial
    detection (PR #4) refreshes the fundamentals cache, the persisted score
    stays stale until the next scheduled scan. This endpoint is the user-
    visible escape hatch: clicking the "refresh score" button on the detail
    page hits this, and the user immediately sees the recomputed pillars.

    The fundamentals fetch is forced (`force_refresh=True`) so even an L1
    entry that was hydrated from a pre-fix partial L2 row still gets
    re-fetched upstream. yfinance circuit breaker still applies — if it's
    open the fundamentals call returns the partial sentinel and the
    recompute proceeds with whatever it gets (some pillars may still be
    None, but the user gets immediate feedback rather than silent failure).
    """
    # Catalog has duplicate ticker rows (CLAUDE.md) — pick any.
    stock = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")

    # Force a fresh fundamentals fetch BEFORE compute_score so it picks up
    # the latest payload. Without this, the L1 might still hold a partial
    # entry from a pre-fix hydration, and the recompute would just produce
    # the same broken score the user already sees.
    try:
        stock_fundamentals_service.get_fundamentals(stock.ticker, force_refresh=True)
    except UpstreamError as exc:
        # Non-fatal: compute_score will still try with whatever cache holds.
        logger.warning(
            f"[score-recompute] upstream {exc.source}.{exc.op} failed for {stock.ticker}: {exc}"
        )
    except Exception as exc:  # noqa: BLE001 — defensive last-resort
        # Non-fatal: compute_score will still try with whatever cache holds.
        logger.exception(
            f"[score-recompute] unexpected error refreshing fundamentals for {stock.ticker}: {exc}"
        )

    new_score = score_service.compute_score(db, stock)
    # UPSERT semantics: a row already exists for this stock_id (the GET would
    # have 404'd otherwise, but we still merge defensively for the case where
    # the user hits POST first on a brand-new ticker before any scan ran).
    db.merge(new_score)
    db.commit()

    try:
        breakdown = json.loads(new_score.breakdown or "{}")
    except json.JSONDecodeError:
        breakdown = {}

    return StockScoreOut(
        stock_id=new_score.stock_id,
        ticker=stock.ticker,
        composite=new_score.composite,
        sub_scores=SubScoresOut(
            quality=new_score.quality,
            profitability=new_score.profitability,
            sustainability=new_score.sustainability,
            growth=new_score.growth,
            value=new_score.value,
            momentum=new_score.momentum,
            sentiment=new_score.sentiment,
        ),
        risk_tier=new_score.risk_tier,  # type: ignore[arg-type]
        computed_at=new_score.computed_at,
        breakdown=breakdown,
        sector_avg=_sector_avg_composite(db, stock.sector),
        **_composite_percentiles(db, stock.sector, new_score.composite),
    )


# ---------------------------------------------------------------------------
# Bulk recompute — user-triggered "Ricalcola tutti gli score" from the
# homepage. Same persistent-toast UX as the alert scan (`/api/alerts/scan`)
# powered by the shared ScanRun-with-kind tracking introduced in 6ed5a4d41b17.
# ---------------------------------------------------------------------------


def _run_recompute_in_background() -> None:
    """BackgroundTask body. Opens its own SessionLocal because FastAPI's
    request-scoped session has already been closed by the time this fires.
    Errors are caught + logged + persisted on the ScanRun row by the runner
    itself, so we don't re-raise here."""
    from app.services.score_runner import run_tracked_recompute

    db = SessionLocal()
    try:
        run_tracked_recompute(db, trigger="manual")
    finally:
        db.close()


@router.post(
    "/scores/recompute-all",
    response_model=ScanAccepted,
    status_code=202,
)
def trigger_recompute_all(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ScanAccepted:
    """Kick off a background recompute of every stock's composite score.

    Returns 202 immediately; the actual work runs via FastAPI's
    BackgroundTask. Live status is polled by the frontend via
    `GET /api/scores/recompute-status`, which feeds the persistent toast.

    Every stock is re-scored on every invocation (the incremental-skip
    optimisation was removed in May 2026 — see score_service.recompute_all
    docstring for the rationale).

    Guards against piling up jobs: if a score_recompute run is already
    in 'running' state we return 409 with a clear message rather than
    spawning a parallel one (the model.merge() collision wouldn't crash
    things, but two concurrent runs would scribble over each other's
    progress heartbeats and confuse the UI).
    """
    already_running = (
        db.execute(
            select(ScanRun)
            .where(
                ScanRun.kind == KIND_SCORE_RECOMPUTE,
                ScanRun.status == "running",
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )
    if already_running is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Ricalcolo già in corso — vedi il toast in basso a destra. "
                "Premi Stop per annullarlo prima di lanciarne un altro."
            ),
        )
    background_tasks.add_task(_run_recompute_in_background)
    return ScanAccepted()


@router.get("/scores/recompute-status", response_model=ScanStatusOut)
def recompute_status(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ScanStatusOut:
    """Most recent score-recompute ScanRun. Empty payload if none has run.

    Mirror of `/api/alerts/scan-status` but filtered to
    `kind='score_recompute'` so the alert-scan toast doesn't pick up
    score-recompute rows and vice versa. Same DTO shape, same staleness
    detection (>2min without heartbeat → `is_stale=True`)."""
    latest = (
        db.execute(
            select(ScanRun)
            .where(ScanRun.kind == KIND_SCORE_RECOMPUTE)
            .order_by(ScanRun.started_at.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )
    if latest is None:
        return ScanStatusOut(is_running=False)
    return build_scan_status_out(latest)


@router.post("/scores/recompute-stop", response_model=ScanStopResult)
def stop_recompute(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ScanStopResult:
    """Stop the latest running score-recompute.

    Mirror of `/api/alerts/scan/stop` filtered by kind:
    - Live worker: cooperative cancel via `scan_cancel.request_cancel`.
      The score_service.recompute_all loop polls this every 10 stocks
      and raises RecomputeCancelled, which run_tracked_recompute catches
      and finalizes the row as 'failed' with 'Cancellato dall'utente'.
    - Orphan row (>2min stale heartbeat): force-close inline since the
      cancel flag would never be checked by a dead worker.
    Idempotent: returns `was_running=False` if there's nothing to stop."""
    from datetime import UTC, datetime

    from app.services import scan_cancel

    latest = (
        db.execute(
            select(ScanRun)
            .where(ScanRun.kind == KIND_SCORE_RECOMPUTE)
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
            message="Nessun ricalcolo da fermare.",
        )
    if latest.status != "running":
        return ScanStopResult(
            stopped_run_id=latest.id,
            was_running=False,
            was_stale=False,
            message=f"Ultimo ricalcolo già in stato '{latest.status}'.",
        )

    status = build_scan_status_out(latest)
    is_stale = status.is_stale

    if is_stale:
        latest.status = "failed"
        latest.phase = None
        latest.error_message = (
            "Worker non risponde da oltre "
            f"{status.seconds_since_last_progress}s — chiusura forzata. "
            "Probabile crash del processo backend."
        )
        latest.completed_at = datetime.now(UTC)
        db.commit()
        scan_cancel.clear(latest.id)
        return ScanStopResult(
            stopped_run_id=latest.id,
            was_running=True,
            was_stale=True,
            message="Ricalcolo bloccato terminato (cleanup forzato).",
        )

    scan_cancel.request_cancel(latest.id)
    return ScanStopResult(
        stopped_run_id=latest.id,
        was_running=True,
        was_stale=False,
        message="Cancellazione richiesta. Il worker si fermerà entro pochi secondi.",
    )


@router.get("/scores/top", response_model=TopPicksOut)
def get_top_picks(
    risk: Annotated[str | None, Query()] = None,
    category: Annotated[str, Query()] = "composite",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TopPicksOut:
    """Top-N stocks by `category` (default: composite), optionally filtered
    by `risk` tier. Returns up to `limit` items (max 50)."""
    if risk is not None and risk not in _VALID_RISK:
        raise HTTPException(
            status_code=422,
            detail=f"risk must be one of {sorted(_VALID_RISK)} or omitted",
        )
    if category not in _VALID_CATEGORY:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {sorted(_VALID_CATEGORY)}",
        )

    sort_col = getattr(StockScore, category)
    q = (
        select(StockScore, Stock)
        .join(Stock, Stock.id == StockScore.stock_id)
        # Hidden-country stocks (CN/JP/KR) should never surface in
        # top-picks — they're catalog-only for breadth/mood. Single
        # source of truth: `app.core.visibility`.
        .where(visible_country_clause())
    )
    if risk is not None:
        q = q.where(StockScore.risk_tier == risk)
    # Skip stocks where the requested sub-score is NULL — those rows shouldn't
    # appear in a "top by quality" list at all (a NULL pillar means missing data).
    if category != "composite":
        q = q.where(sort_col.isnot(None))
    # Over-fetch: the confidence gate below drops some rows, so pull a
    # generous candidate pool (capped) and truncate to `limit` after
    # filtering. Coverage is JSON inside a Text column → can't filter in
    # SQL on SQLite cleanly; doing it in Python over a bounded pool is
    # simplest and keeps the downstream per-stock change_pct loop small.
    q = q.order_by(sort_col.desc()).limit(min(limit * 6, 300))

    candidate_rows = db.execute(q).all()

    def _confidence(s: StockScore) -> float | None:
        try:
            mg = json.loads(s.breakdown or "{}").get("_meta_global") or {}
        except (json.JSONDecodeError, TypeError):
            return None
        c = mg.get("coverage")
        return float(c) if isinstance(c, (int, float)) else None

    rows = [
        (sc, st)
        for (sc, st) in candidate_rows
        if (_cov := _confidence(sc)) is not None and _cov >= _MIN_CONFIDENCE
    ][:limit]

    # change_pct: most-recent two close prices per stock. Batch-fetch the last
    # two bars for all stocks in the result set in one query — avoids N+1.
    stock_ids = [s.id for _, s in rows]
    change_by_stock: dict[int, float] = {}
    if stock_ids:
        # Pull last 2 close prices per stock_id. Doing this with a window
        # function in SQLite is awkward; for ≤50 stocks the per-stock query is
        # fine and keeps the code simple.
        for sid in stock_ids:
            last_two = db.execute(
                select(OhlcvDaily.close)
                .where(OhlcvDaily.stock_id == sid)
                .order_by(OhlcvDaily.date.desc())
                .limit(2)
            ).scalars().all()
            if len(last_two) >= 2:
                last_c = float(last_two[0])
                prev_c = float(last_two[1])
                if prev_c:
                    change_by_stock[sid] = (last_c - prev_c) / prev_c * 100.0

    items: list[TopPickItemOut] = []
    for score, stock in rows:
        items.append(
            TopPickItemOut(
                stock_id=stock.id,
                ticker=stock.ticker,
                name=stock.name,
                composite=score.composite,
                risk_tier=score.risk_tier,  # type: ignore[arg-type]
                sector=stock.sector,
                market_cap=stock.market_cap,
                change_pct=change_by_stock.get(stock.id),
            )
        )
    return TopPicksOut(
        category=category,  # type: ignore[arg-type]
        risk=risk,  # type: ignore[arg-type]
        items=items,
    )
