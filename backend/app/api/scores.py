"""Score API: per-stock score breakdown + cross-universe top picks.

Both endpoints require auth (consistent with the rest of /api). The single-
stock endpoint returns the persisted breakdown verbatim — the UI walks the
dict to render component bars without re-fetching upstream data.
"""
import json
from typing import Annotated, get_args

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.visibility import visible_country_clause
from app.models import OhlcvDaily, Stock, StockScore, User
from app.schemas.score import (
    RiskTier,
    ScoreCategory,
    StockScoreOut,
    SubScoresOut,
    TopPickItemOut,
    TopPicksOut,
)
from app.services import score_service, stock_fundamentals_service

router = APIRouter(prefix="/api", tags=["scores"])


_VALID_RISK = set(get_args(RiskTier))
_VALID_CATEGORY = set(get_args(ScoreCategory))


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
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: compute_score will still try with whatever cache holds.
        logger.warning(
            f"[score-recompute] fundamentals refresh failed for {stock.ticker}: {exc}"
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
    q = q.order_by(sort_col.desc()).limit(limit)

    rows = db.execute(q).all()

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
