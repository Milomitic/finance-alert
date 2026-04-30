"""Stock router."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Stock, User
from app.schemas.stock import FilterOptionsOut, IndexOptionOut, StockOut, StockSearchOut
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
