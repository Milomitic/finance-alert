"""Market detail endpoint — `/api/markets/{symbol}/detail`.

Serves OHLCV history + summary fields for non-stock instruments
(indices, commodities, crypto) that are listed in the dashboard's
LiveAssetsPanel. Used by the frontend MarketDetailPage.

Why a separate router from `/api/stocks/...`
- Catalog membership: those endpoints filter via the catalog +
  `visible_country_clause`. The symbols here (^GSPC, BTC-USD, GC=F,
  ...) intentionally aren't in the catalog.
- Different fetch path: `services/market_detail_service` goes
  straight to yfinance with a 15-min cache, no DB roundtrip for
  the OHLCV.
"""
from datetime import date as date_t
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.market import LIVE_ASSET_DEFINITIONS
from app.models import User
from app.services import live_quote_service, market_detail_service

router = APIRouter(prefix="/api/markets", tags=["markets"])


# Build a quick lookup of the curated symbols + their UI metadata so
# the detail endpoint can return name/category/flag without the
# frontend hard-coding it.
_LIVE_META: dict[str, tuple[str, str, str | None]] = {
    symbol: (name, category, flag)
    for (symbol, name, category, flag) in LIVE_ASSET_DEFINITIONS
}


class OhlcvBarOut(BaseModel):
    date: date_t
    open: float
    high: float
    low: float
    close: float
    volume: int | None


class LiveQuoteOut(BaseModel):
    """Subset of live_quote_service.LiveQuote relevant to non-stocks."""
    price: float | None
    prev_close: float | None
    change_abs: float | None
    change_pct: float | None
    market_state: str | None
    currency: str | None
    error: str | None


class MarketDetailOut(BaseModel):
    symbol: str
    name: str
    category: str  # "index" | "commodity" | "crypto"
    flag: str | None
    range_key: str

    last_close: float | None
    prev_close: float | None
    change_pct: float | None
    high_window: float | None
    low_window: float | None
    high_52w: float | None
    low_52w: float | None

    bars: list[OhlcvBarOut]
    quote: LiveQuoteOut | None


@router.get("/{symbol}/detail", response_model=MarketDetailOut)
def get_market_detail(
    symbol: str,
    range: Annotated[str, Query()] = "1d",
    _user: User = Depends(get_current_user),
) -> MarketDetailOut:
    if range not in (
        "30m", "1h", "4h", "1d", "1w", "1m", "all",
        # legacy compat for old URLs/bookmarks
        "1y", "3m", "6m", "5y",
    ):
        raise HTTPException(status_code=422, detail="invalid timeframe")

    meta = _LIVE_META.get(symbol)
    if meta is None:
        # Not one of the curated symbols. We could still try yfinance
        # blindly, but exposing arbitrary symbol fetch invites abuse —
        # the only consumer is the LiveAssetsPanel, so refusing
        # uncurated symbols is safer.
        raise HTTPException(status_code=404, detail="Unknown market symbol")
    name, category, flag = meta

    detail = market_detail_service.get_detail(symbol, range)
    if detail is None:
        raise HTTPException(status_code=404, detail="No market data available")

    quote_out: LiveQuoteOut | None = None
    try:
        q = live_quote_service.get_quote(symbol)
        if q is not None:
            quote_out = LiveQuoteOut(
                price=q.price,
                prev_close=q.prev_close,
                change_abs=q.change_abs,
                change_pct=q.change_pct,
                market_state=q.market_state,
                currency=q.currency,
                error=q.error,
            )
    except Exception:  # noqa: BLE001
        # Quote is best-effort; the chart still renders without it.
        quote_out = None

    return MarketDetailOut(
        symbol=symbol,
        name=name,
        category=category,
        flag=flag,
        range_key=detail.range_key,
        last_close=detail.last_close,
        prev_close=detail.prev_close,
        change_pct=detail.change_pct,
        high_window=detail.high_window,
        low_window=detail.low_window,
        high_52w=detail.high_52w,
        low_52w=detail.low_52w,
        bars=[
            OhlcvBarOut(
                date=b.date,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in detail.bars
        ],
        quote=quote_out,
    )
