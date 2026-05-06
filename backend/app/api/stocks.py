"""Stock router."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.core.visibility import visible_country_clause
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Stock, User
from app.schemas.alert import AlertOut
from app.schemas.stock import (
    FilterOptionsOut, IndexOptionOut, StockOut, StockScoreRefOut,
    StockSearchItemOut, StockSearchOut,
)
from app.schemas.stock_detail import (
    AnalystActionOut, AnalystPriceTargetOut, AnalystRatingOut,
    CompanyProfileOut, EffectiveRuleOut,
    FundamentalsAnnualOut, FundamentalsEarningsOut, FundamentalsOut,
    FundamentalsQuarterlyOut, IndicatorPeriodsOut, IndicatorPointOut, IndicatorSeriesOut,
    InsiderTransactionOut, LiveQuoteOut, LiveQuotesBatchOut, MicroDataOut,
    OhlcvBarOut, StockDetailOut, StockKpisOut, StockNewsItemOut, StockNewsOut,
)
from app.services import (
    live_quote_service, stock_detail_service, stock_fundamentals_service,
    stock_news_service,
)
from app.services.stock_service import (
    SORTABLE_COLUMNS, StockFilter, get_filter_options, search_stocks,
)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search", response_model=StockSearchOut)
def search(
    q: str | None = None,
    exchange: Annotated[list[str] | None, Query()] = None,
    sector: Annotated[list[str] | None, Query()] = None,
    industry: Annotated[list[str] | None, Query()] = None,
    country: Annotated[list[str] | None, Query()] = None,
    index: Annotated[list[str] | None, Query()] = None,
    risk: Annotated[list[str] | None, Query()] = None,
    min_score: float | None = None,
    sort_by: str = "ticker",
    sort_dir: str = "asc",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockSearchOut:
    if sort_by not in SORTABLE_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"sort_by must be one of {sorted(SORTABLE_COLUMNS.keys())}",
        )
    if sort_dir not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="sort_dir must be 'asc' or 'desc'")
    if risk:
        valid_risk = {"conservative", "moderate", "aggressive"}
        bad = [r for r in risk if r not in valid_risk]
        if bad:
            raise HTTPException(
                status_code=422,
                detail=f"risk must be one of {sorted(valid_risk)}; got {bad}",
            )
    if min_score is not None and not (0.0 <= min_score <= 100.0):
        raise HTTPException(status_code=422, detail="min_score must be in [0, 100]")
    page = search_stocks(
        db,
        StockFilter(
            q=q,
            exchanges=exchange or [],
            sectors=sector or [],
            industries=industry or [],
            countries=country or [],
            index_codes=index or [],
            risk_tiers=risk or [],
            min_score=min_score,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        ),
    )
    return StockSearchOut(
        items=[
            StockSearchItemOut(
                stock=StockOut.model_validate(item.stock),
                score=StockScoreRefOut(
                    composite=item.score.composite,
                    risk_tier=item.score.risk_tier,
                ),
            )
            for item in page.items
        ],
        total=page.total,
        has_more=page.has_more,
    )


@router.get("/filters", response_model=FilterOptionsOut)
def filters(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> FilterOptionsOut:
    opts = get_filter_options(db)
    return FilterOptionsOut(
        exchanges=opts.exchanges,
        sectors=opts.sectors,
        industries=opts.industries,
        countries=opts.countries,
        indices=[IndexOptionOut(code=i.code, name=i.name) for i in opts.indices],
    )


@router.get("/{ticker}", response_model=StockOut)
def get_one(
    ticker: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> StockOut:
    # `ticker` è univoco a livello di catalogo dopo `dedupe_stocks` +
    # canonicalizzazione in seed/catalog refresh: usiamo
    # `scalar_one_or_none()` per fail-loud se qualcuno reintroduce
    # duplicati (più sicuro di `.first()` che li nasconderebbe).
    # Hidden countries (CN/JP/KR) → 404 for deep links. Single source
    # of truth: `app.core.visibility`.
    stock = db.execute(
        select(Stock).where(
            Stock.ticker == ticker,
            visible_country_clause(),
        )
    ).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
    return StockOut.model_validate(stock)


@router.get("/{ticker}/detail", response_model=StockDetailOut)
def get_stock_detail(
    ticker: str,
    range: str = "1y",
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockDetailOut:
    # v2 timeframe vocabulary: 30m/1h are intraday (yfinance live),
    # 1d/1w/1m/all are daily-resolution (DB-backed for catalog stocks).
    # Legacy keys (1y/3m/6m/5y/4h) accepted for backward-compat URLs and
    # mapped to nearest equivalent. 4h was dropped because yfinance
    # hourly bars don't divide cleanly into 4h boundaries — see
    # `services/timeframe_service.py` for the full rationale.
    LEGACY_TF_MAP = {"1y": "1d", "3m": "1h", "6m": "1h", "5y": "1w", "4h": "1h"}
    if range in LEGACY_TF_MAP:
        range = LEGACY_TF_MAP[range]
    if range not in ("30m", "1h", "1d", "1w", "1m", "all"):
        raise HTTPException(status_code=422, detail="invalid timeframe")
    detail = stock_detail_service.get_detail(db, ticker, range_key=range)
    if detail is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
    return StockDetailOut(
        stock=StockOut.model_validate(detail.stock),
        ohlcv=[
            OhlcvBarOut(
                date=b.date, open=float(b.open), high=float(b.high),
                low=float(b.low), close=float(b.close), volume=int(b.volume),
            )
            for b in detail.ohlcv
        ],
        indicators=IndicatorSeriesOut(
            sma20=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.sma20],
            sma50=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.sma50],
            sma200=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.sma200],
            rsi14=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.rsi14],
            bb_upper=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.bb_upper],
            bb_middle=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.bb_middle],
            bb_lower=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.bb_lower],
            macd_line=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.macd_line],
            macd_signal=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.macd_signal],
            macd_hist=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.macd_hist],
            periods=IndicatorPeriodsOut(**detail.indicator_periods.__dict__),
        ),
        kpis=StockKpisOut(
            last_close=detail.kpis.last_close, prev_close=detail.kpis.prev_close,
            change_pct=detail.kpis.change_pct,
            high_52w=detail.kpis.high_52w, low_52w=detail.kpis.low_52w,
            vol_avg_20=detail.kpis.vol_avg_20, vol_today=detail.kpis.vol_today,
            vol_ratio=detail.kpis.vol_ratio,
        ),
        effective_rules=[
            EffectiveRuleOut(
                kind=r.kind, enabled=r.enabled, params=r.params,
                source=r.source, watchlist_name=r.watchlist_name,
            )
            for r in detail.effective_rules
        ],
        alerts_history=[
            AlertOut(
                id=a.id, rule_id=a.rule_id, rule_kind=rule_kind,
                stock_id=a.stock_id, ticker=detail.stock.ticker,
                name=detail.stock.name,
                triggered_at=a.triggered_at, signal_date=a.signal_date,
                trigger_price=float(a.trigger_price),
                snapshot=__import__("json").loads(a.snapshot or "{}"),
                read_at=a.read_at, archived_at=a.archived_at,
            )
            for (a, rule_kind) in detail.alerts_history
        ],
    )


@router.get("/{ticker}/news", response_model=StockNewsOut)
def get_stock_news(
    ticker: str,
    limit: int = 5,
    _user: User = Depends(get_current_user),
) -> StockNewsOut:
    """Fetch up to `limit` news items, most-recent-first.

    yfinance typically returns 10–20 items per ticker. Cap raised from 20 to 50
    so a UI that wants to render a long scrollable list isn't artificially
    truncated; the cache layer means the wider limit doesn't cost extra
    upstream calls.
    """
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=422, detail="limit must be 1..50")
    items = stock_news_service.get_news(ticker, limit=limit)
    return StockNewsOut(items=[StockNewsItemOut(**n) for n in items])


@router.get("/{ticker}/fundamentals", response_model=FundamentalsOut)
def get_stock_fundamentals(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> FundamentalsOut:
    """Annual revenue/net income/EPS + earnings history with surprise %.
    Cached 24h; non-fatal on yfinance failure (returns empty payload)."""
    # `ticker` è univoco — vedi nota in `get_one()`.
    stock = db.execute(
        select(Stock).where(Stock.ticker == ticker)
    ).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")
    f = stock_fundamentals_service.get_fundamentals(ticker)
    return FundamentalsOut(
        ticker=f.ticker,
        annual=[FundamentalsAnnualOut(**a.__dict__) for a in f.annual],
        quarterly=[FundamentalsQuarterlyOut(**q.__dict__) for q in f.quarterly],
        earnings=[FundamentalsEarningsOut(**e.__dict__) for e in f.earnings],
        next_earnings_date=f.next_earnings_date,
        next_eps_estimate=f.next_eps_estimate,
        next_revenue_estimate=f.next_revenue_estimate,
        micro=MicroDataOut(**f.micro.__dict__),
        profile=CompanyProfileOut(**f.profile.__dict__),
        insiders=[InsiderTransactionOut(**i.__dict__) for i in f.insiders],
        analyst_ratings=[AnalystRatingOut(**r.__dict__) for r in f.analyst_ratings],
        analyst_actions=[AnalystActionOut(**a.__dict__) for a in f.analyst_actions],
        price_target=AnalystPriceTargetOut(**f.price_target.__dict__),
        error=f.error,
    )


@router.get("/quotes", response_model=LiveQuotesBatchOut)
def get_quotes_batch(
    tickers: str,    # comma-separated
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> LiveQuotesBatchOut:
    """Live (10s-cached) quotes for up to 50 tickers in one request.

    Format: ?tickers=AAPL,MSFT,GOOGL — comma-separated. Order in the
    response matches the request order. Unknown tickers (not in catalog)
    are skipped silently rather than 404'ing the whole batch.
    """
    requested = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not requested:
        raise HTTPException(status_code=422, detail="tickers query param required")
    if len(requested) > 50:
        raise HTTPException(status_code=422, detail="max 50 tickers per request")
    # Filter to tickers we know about (avoid hitting Yahoo for typos)
    known = set(
        db.execute(select(Stock.ticker).where(Stock.ticker.in_(requested)))
        .scalars().all()
    )
    valid = [t for t in requested if t in known]
    quotes_map = live_quote_service.get_quotes_batch(valid)
    return LiveQuotesBatchOut(
        quotes=[LiveQuoteOut(**quotes_map[t].__dict__) for t in valid if t in quotes_map],
    )


@router.get("/{ticker}/quote", response_model=LiveQuoteOut)
def get_stock_quote(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> LiveQuoteOut:
    """Live (10s-cached) quote for a single ticker. Honors the yfinance
    circuit breaker — returns the cached quote (with `error` set) when
    Yahoo is rate-limited rather than blocking the request."""
    # `ticker` è univoco — vedi nota in `get_one()`.
    exists = db.execute(
        select(Stock.id).where(Stock.ticker == ticker)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")
    q = live_quote_service.get_quote(ticker)
    return LiveQuoteOut(**q.__dict__)
