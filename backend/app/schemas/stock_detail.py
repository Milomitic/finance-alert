"""Pydantic schemas for /api/stocks/{ticker}/detail and /news."""
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.alert import AlertOut
from app.schemas.stock import StockOut


class OhlcvBarOut(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class IndicatorPointOut(BaseModel):
    date: date
    value: float | None


class FundamentalsAnnualOut(BaseModel):
    fiscal_year_end: str
    revenue: float | None
    net_income: float | None
    eps: float | None


class FundamentalsEarningsOut(BaseModel):
    date: str
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None


class FundamentalsOut(BaseModel):
    ticker: str
    annual: list[FundamentalsAnnualOut] = []
    earnings: list[FundamentalsEarningsOut] = []
    next_earnings_date: str | None = None
    next_eps_estimate: float | None = None
    error: str | None = None


class IndicatorSeriesOut(BaseModel):
    sma20: list[IndicatorPointOut] = []
    sma50: list[IndicatorPointOut]
    sma200: list[IndicatorPointOut]
    rsi14: list[IndicatorPointOut]
    bb_upper: list[IndicatorPointOut] = []
    bb_middle: list[IndicatorPointOut] = []
    bb_lower: list[IndicatorPointOut] = []
    macd_line: list[IndicatorPointOut] = []
    macd_signal: list[IndicatorPointOut] = []
    macd_hist: list[IndicatorPointOut] = []


class StockKpisOut(BaseModel):
    last_close: float | None
    prev_close: float | None
    change_pct: float | None
    high_52w: float | None
    low_52w: float | None
    vol_avg_20: float | None
    vol_today: int | None
    vol_ratio: float | None


class EffectiveRuleOut(BaseModel):
    kind: str
    enabled: bool
    params: dict[str, Any]
    source: str
    watchlist_name: str | None


class StockDetailOut(BaseModel):
    stock: StockOut
    ohlcv: list[OhlcvBarOut]
    indicators: IndicatorSeriesOut
    kpis: StockKpisOut
    effective_rules: list[EffectiveRuleOut]
    alerts_history: list[AlertOut]


class StockNewsItemOut(BaseModel):
    title: str
    link: str
    publisher: str
    published_at: str | None


class StockNewsOut(BaseModel):
    items: list[StockNewsItemOut]
