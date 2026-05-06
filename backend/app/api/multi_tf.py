"""Multi-timeframe KPI comparison endpoints.

Backs the `<MultiTimeframeKpisCard>` panel on the stock-detail and
market-detail pages: one row per timeframe (30m / 1h / 1d / 1w / 1m
/ all) showing the latest indicator readings + composite
bullish/bearish score for that timeframe.

Two endpoints share the same payload shape:
  GET /api/stocks/{ticker}/multi-tf-kpis
  GET /api/markets/{symbol}/multi-tf-kpis

The split exists for the same reason as the existing detail
endpoints: stock tickers go through the catalog (DB-backed daily
when possible), market symbols always go straight to yfinance.
Internally both call `services.timeframe_service.compute_timeframe_kpis`
with the unified `fetch_bars()` helper that handles the source
selection automatically.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.market import LIVE_ASSET_DEFINITIONS
from app.core.visibility import visible_country_clause
from app.models import Stock, User
from app.services.timeframe_service import (
    VALID_TIMEFRAMES,
    compute_timeframe_kpis,
    fetch_bars,
)

router = APIRouter(tags=["multi-tf"])


class TimeframeKpisOut(BaseModel):
    timeframe: str
    bars: int
    last_close: float | None
    rsi: float | None
    rsi_tone: str
    sma20: float | None
    sma50: float | None
    sma200: float | None
    sma20_above: bool | None
    sma50_above: bool | None
    sma200_above: bool | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    bb_position: float | None
    macd_line: float | None
    macd_signal: float | None
    macd_hist: float | None
    macd_tone: str
    composite_score: int
    composite_label: str


class MultiTfKpisOut(BaseModel):
    ticker: str
    items: list[TimeframeKpisOut]


def _to_out(kpis: Any) -> TimeframeKpisOut:
    return TimeframeKpisOut(
        timeframe=kpis.timeframe,
        bars=kpis.bars,
        last_close=kpis.last_close,
        rsi=kpis.rsi,
        rsi_tone=kpis.rsi_tone,
        sma20=kpis.sma20,
        sma50=kpis.sma50,
        sma200=kpis.sma200,
        sma20_above=kpis.sma20_above,
        sma50_above=kpis.sma50_above,
        sma200_above=kpis.sma200_above,
        bb_upper=kpis.bb_upper,
        bb_middle=kpis.bb_middle,
        bb_lower=kpis.bb_lower,
        bb_position=kpis.bb_position,
        macd_line=kpis.macd_line,
        macd_signal=kpis.macd_signal,
        macd_hist=kpis.macd_hist,
        macd_tone=kpis.macd_tone,
        composite_score=kpis.composite_score,
        composite_label=kpis.composite_label,
    )


@router.get(
    "/api/stocks/{ticker}/multi-tf-kpis",
    response_model=MultiTfKpisOut,
)
def get_stock_multi_tf_kpis(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MultiTfKpisOut:
    """Compute KPIs for a catalog stock across all 7 timeframes.
    Daily-resolution timeframes pull from DB (fast); intraday hits
    yfinance with a 5-min cache. Hidden countries (CN/JP/KR) 404
    here too — same rule as the rest of the user-facing surfaces."""
    stock = db.execute(
        Stock.__table__.select()
        .where(Stock.ticker == ticker)
        .where(visible_country_clause())
    ).first()
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
    # Re-resolve to ORM instance (the .select() above gives a Row)
    from sqlalchemy import select as sql_select

    stock_orm = db.execute(
        sql_select(Stock).where(Stock.id == stock.id)
    ).scalar_one()
    items: list[TimeframeKpisOut] = []
    for tf in VALID_TIMEFRAMES:
        bars = fetch_bars(ticker=ticker, timeframe=tf, db=db, stock=stock_orm)
        kpis = compute_timeframe_kpis(bars, tf)
        items.append(_to_out(kpis))
    return MultiTfKpisOut(ticker=ticker, items=items)


@router.get(
    "/api/markets/{symbol}/multi-tf-kpis",
    response_model=MultiTfKpisOut,
)
def get_market_multi_tf_kpis(
    symbol: str,
    _user: User = Depends(get_current_user),
) -> MultiTfKpisOut:
    """Same shape as the stock variant but for non-catalog symbols
    (^GSPC, BTC-USD, GC=F, …) listed in the dashboard's
    LiveAssetsPanel. yfinance for everything; no DB roundtrip."""
    valid_symbols = {d[0] for d in LIVE_ASSET_DEFINITIONS}
    if symbol not in valid_symbols:
        raise HTTPException(status_code=404, detail="Unknown market symbol")
    items: list[TimeframeKpisOut] = []
    for tf in VALID_TIMEFRAMES:
        bars = fetch_bars(ticker=symbol, timeframe=tf)
        kpis = compute_timeframe_kpis(bars, tf)
        items.append(_to_out(kpis))
    return MultiTfKpisOut(ticker=symbol, items=items)
