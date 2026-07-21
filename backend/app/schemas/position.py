"""Pydantic schemas for /api/positions (tracked trades, B3-6)."""
from datetime import datetime

from pydantic import BaseModel, Field


class PositionOut(BaseModel):
    """One position enriched read-time by `position_service._enrich`:
    `last_price`/`unrealized_*` are live-quote-derived for OPEN positions
    (`price_source` = "live" | "eod" fallback | None when neither exists);
    `realized_*` come from the stored exit_price for CLOSED ones. The `_abs`
    figures are None for notional-only positions (no size)."""
    id: int
    stock_id: int
    ticker: str
    name: str | None
    alert_id: int | None
    side: str
    entry_price: float
    stop_price: float | None
    target_price: float | None
    size: float | None
    opened_at: datetime
    closed_at: datetime | None
    exit_price: float | None
    exit_reason: str | None
    notes: str | None
    last_price: float | None
    price_source: str | None
    unrealized_pct: float | None
    unrealized_abs: float | None
    realized_pct: float | None
    realized_abs: float | None
    # Native currency of the position (= the stock's currency) + the abs P&L
    # converted to USD, so the portfolio rollup can sum across currencies.
    currency: str | None = None
    unrealized_usd: float | None = None
    realized_usd: float | None = None
    cost_usd: float | None = None


class PositionCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    side: str = Field(default="long", pattern=r"^(long|short)$")
    # None → the backend defaults to the live price (last stored close as
    # fallback) at open time.
    entry_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    target_price: float | None = Field(default=None, gt=0)
    # Share count; None = notional-only tracking (P&L in % only).
    size: float | None = Field(default=None, gt=0)
    alert_id: int | None = None
    notes: str | None = Field(default=None, max_length=1000)


class PositionUpdate(BaseModel):
    """PATCH body: `close=True` closes manually (exit_price defaults to the
    live/last price); otherwise edits stop/target/notes of an open position."""
    close: bool = False
    exit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    target_price: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=1000)
