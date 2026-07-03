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
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.market import LIVE_ASSET_DEFINITIONS
from app.core.visibility import visible_country_clause
from app.models import Stock, User
from app.services.timeframe_service import (
    _INTRADAY,
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
    ema20: float | None
    ema50: float | None
    ema200: float | None
    ema20_above: bool | None
    ema50_above: bool | None
    ema200_above: bool | None
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


def _compute_multi_tf(
    ticker: str, *, db: Session | None = None, stock: Stock | None = None
) -> list[TimeframeKpisOut]:
    """KPIs across every timeframe.

    The timeframes were fetched in a serial loop, so a stock detail page paid
    three back-to-back yfinance round-trips (5m/30m/1h) plus the DB reads. Those
    intraday fetches are independent network calls → run them concurrently so
    their latencies overlap instead of summing. DB-backed timeframes stay on the
    calling thread because the SQLAlchemy Session is not thread-safe; a market
    symbol (no `db`) hits yfinance for everything and parallelizes all of them."""
    if db is not None:
        yf_tfs = [tf for tf in VALID_TIMEFRAMES if tf in _INTRADAY]
        db_tfs = [tf for tf in VALID_TIMEFRAMES if tf not in _INTRADAY]
    else:
        yf_tfs = list(VALID_TIMEFRAMES)
        db_tfs = []

    results: dict[str, Any] = {}
    for tf in db_tfs:
        results[tf] = compute_timeframe_kpis(
            fetch_bars(ticker=ticker, timeframe=tf, db=db, stock=stock), tf
        )
    if yf_tfs:
        # No db/stock passed → the workers never touch the Session.
        with ThreadPoolExecutor(max_workers=len(yf_tfs)) as ex:
            futures = {
                ex.submit(fetch_bars, ticker=ticker, timeframe=tf): tf
                for tf in yf_tfs
            }
            for fut, tf in futures.items():
                results[tf] = compute_timeframe_kpis(fut.result(), tf)

    return [_to_out(results[tf]) for tf in VALID_TIMEFRAMES]


def _to_out(kpis: Any) -> TimeframeKpisOut:
    return TimeframeKpisOut(
        timeframe=kpis.timeframe,
        bars=kpis.bars,
        last_close=kpis.last_close,
        rsi=kpis.rsi,
        rsi_tone=kpis.rsi_tone,
        ema20=kpis.ema20,
        ema50=kpis.ema50,
        ema200=kpis.ema200,
        ema20_above=kpis.ema20_above,
        ema50_above=kpis.ema50_above,
        ema200_above=kpis.ema200_above,
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
    items = _compute_multi_tf(ticker, db=db, stock=stock_orm)
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
    items = _compute_multi_tf(symbol)  # no db → all timeframes via yfinance
    return MultiTfKpisOut(ticker=symbol, items=items)
