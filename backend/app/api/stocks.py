"""Stock router."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Stock, User
from app.schemas.alert import AlertOut
from app.schemas.stock import FilterOptionsOut, IndexOptionOut, StockOut, StockSearchOut
from app.schemas.stock_detail import (
    EffectiveRuleOut, IndicatorPointOut, IndicatorSeriesOut, OhlcvBarOut,
    StockDetailOut, StockKpisOut, StockNewsItemOut, StockNewsOut,
)
from app.services import stock_detail_service, stock_news_service
from app.services.stock_service import StockFilter, get_filter_options, search_stocks

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search", response_model=StockSearchOut)
def search(
    q: str | None = None,
    exchange: Annotated[list[str] | None, Query()] = None,
    sector: Annotated[list[str] | None, Query()] = None,
    country: Annotated[list[str] | None, Query()] = None,
    index: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockSearchOut:
    page = search_stocks(
        db,
        StockFilter(
            q=q,
            exchanges=exchange or [],
            sectors=sector or [],
            countries=country or [],
            index_codes=index or [],
            limit=limit,
            offset=offset,
        ),
    )
    return StockSearchOut(
        items=[StockOut.model_validate(s) for s in page.items],
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
        countries=opts.countries,
        indices=[IndexOptionOut(code=i.code, name=i.name) for i in opts.indices],
    )


@router.get("/{ticker}", response_model=StockOut)
def get_one(
    ticker: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> StockOut:
    stock = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()
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
    if range not in ("1m", "3m", "6m", "1y", "all"):
        raise HTTPException(status_code=422, detail="invalid range")
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
            sma50=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.sma50],
            sma200=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.sma200],
            rsi14=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.rsi14],
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
                id=a.id, rule_id=a.rule_id, rule_kind=None,
                stock_id=a.stock_id, ticker=detail.stock.ticker,
                triggered_at=a.triggered_at, trigger_price=float(a.trigger_price),
                snapshot=__import__("json").loads(a.snapshot or "{}"),
                read_at=a.read_at, archived_at=a.archived_at,
            )
            for a in detail.alerts_history
        ],
    )


@router.get("/{ticker}/news", response_model=StockNewsOut)
def get_stock_news(
    ticker: str,
    limit: int = 5,
    _user: User = Depends(get_current_user),
) -> StockNewsOut:
    if limit < 1 or limit > 20:
        raise HTTPException(status_code=422, detail="limit must be 1..20")
    items = stock_news_service.get_news(ticker, limit=limit)
    return StockNewsOut(items=[StockNewsItemOut(**n) for n in items])
