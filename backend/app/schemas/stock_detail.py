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


class LiveQuoteOut(BaseModel):
    ticker: str
    price: float | None = None
    prev_close: float | None = None
    change_abs: float | None = None
    change_pct: float | None = None
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: int | None = None
    market_state: str | None = None
    currency: str | None = None
    fetched_at: float = 0.0
    error: str | None = None


class LiveQuotesBatchOut(BaseModel):
    quotes: list[LiveQuoteOut]


class FundamentalsAnnualOut(BaseModel):
    fiscal_year_end: str
    revenue: float | None
    net_income: float | None
    eps: float | None


class FundamentalsQuarterlyOut(BaseModel):
    fiscal_quarter_end: str
    revenue: float | None
    eps: float | None


class FundamentalsEarningsOut(BaseModel):
    date: str
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None
    revenue_estimate: float | None = None
    revenue_reported: float | None = None


class MicroDataOut(BaseModel):
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    beta: float | None = None
    dividend_yield: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_to_ebitda: float | None = None
    enterprise_value: float | None = None
    book_value: float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    profit_margins: float | None = None
    operating_margins: float | None = None
    gross_margins: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    free_cashflow: float | None = None
    operating_cashflow: float | None = None
    payout_ratio: float | None = None
    held_percent_insiders: float | None = None
    held_percent_institutions: float | None = None
    fifty_two_week_change: float | None = None
    sp500_fifty_two_week_change: float | None = None


class InsiderTransactionOut(BaseModel):
    insider: str
    position: str
    transaction: str
    date: str
    shares: int | None
    value: float | None


class AnalystRatingOut(BaseModel):
    period: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


class AnalystPriceTargetOut(BaseModel):
    current: float | None
    low: float | None
    mean: float | None
    median: float | None
    high: float | None


class AnalystActionOut(BaseModel):
    date: str
    firm: str
    to_grade: str
    from_grade: str
    action: str


class FundamentalsOut(BaseModel):
    ticker: str
    annual: list[FundamentalsAnnualOut] = []
    quarterly: list[FundamentalsQuarterlyOut] = []
    earnings: list[FundamentalsEarningsOut] = []
    next_earnings_date: str | None = None
    next_eps_estimate: float | None = None
    micro: MicroDataOut = MicroDataOut()
    insiders: list[InsiderTransactionOut] = []
    analyst_ratings: list[AnalystRatingOut] = []
    analyst_actions: list[AnalystActionOut] = []
    price_target: AnalystPriceTargetOut = AnalystPriceTargetOut(
        current=None, low=None, mean=None, median=None, high=None
    )
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
