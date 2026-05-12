"""Pydantic schemas for /api/stocks/{ticker}/detail and /news."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.alert import AlertOut
from app.schemas.stock import StockOut


class OhlcvBarOut(BaseModel):
    # `date | datetime` — daily bars carry a date-only YYYY-MM-DD;
    # intraday (30m/1h) carry full datetime so each bar gets a unique
    # timestamp on the chart. Without the datetime variant for intraday,
    # all 13 30-min bars of a single trading day collapsed onto the
    # same time and the chart blanked out (see commit history).
    date: date | datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class IndicatorPointOut(BaseModel):
    # Same as OhlcvBarOut.date — intraday timestamps preserve hour:min so
    # indicator overlays align with the bars on the chart.
    date: date | datetime
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
    """Mirror of `services.stock_fundamentals_service.MicroData`.
    Comprehensive coverage of yfinance Ticker.info numeric fields. All
    optional — yfinance returns different subsets per ticker."""
    # Valuation multiples
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    trailing_peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_to_ebitda: float | None = None
    enterprise_to_revenue: float | None = None
    enterprise_value: float | None = None
    book_value: float | None = None
    price_eps_current_year: float | None = None
    # Profitability / margins
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    profit_margins: float | None = None
    operating_margins: float | None = None
    gross_margins: float | None = None
    ebitda_margins: float | None = None
    ebitda: float | None = None
    gross_profits: float | None = None
    net_income_to_common: float | None = None
    # Earnings / EPS
    eps_trailing: float | None = None
    eps_forward: float | None = None
    eps_current_year: float | None = None
    earnings_quarterly_growth: float | None = None
    # Revenue
    total_revenue: float | None = None
    revenue_per_share: float | None = None
    # Leverage / liquidity
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    total_cash: float | None = None
    total_cash_per_share: float | None = None
    total_debt: float | None = None
    # Cash flow
    free_cashflow: float | None = None
    operating_cashflow: float | None = None
    # Growth
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    # Dividend
    dividend_rate: float | None = None
    dividend_yield: float | None = None
    five_year_avg_dividend_yield: float | None = None
    trailing_annual_dividend_rate: float | None = None
    trailing_annual_dividend_yield: float | None = None
    payout_ratio: float | None = None
    # Beta / risk
    beta: float | None = None
    # Shares / float / short interest
    shares_outstanding: float | None = None
    float_shares: float | None = None
    shares_short: float | None = None
    short_ratio: float | None = None
    short_percent_of_float: float | None = None
    # Holdings
    held_percent_insiders: float | None = None
    held_percent_institutions: float | None = None
    # Analyst aggregate
    recommendation_mean: float | None = None
    number_of_analyst_opinions: float | None = None
    # Performance vs market
    fifty_two_week_change: float | None = None
    sp500_fifty_two_week_change: float | None = None
    # Governance / risk scores (Yahoo's 1-10 scales)
    audit_risk: float | None = None
    board_risk: float | None = None
    compensation_risk: float | None = None
    share_holder_rights_risk: float | None = None
    overall_risk: float | None = None


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
    # Optional per-analyst price target fields. Recent yfinance versions
    # expose these via upgrades_downgrades; older versions don't, in which
    # case all three are None and the UI shows a placeholder. See the
    # AnalystAction dataclass docstring for context.
    current_price_target: float | None = None
    prior_price_target: float | None = None
    price_target_action: str | None = None
    # News-extracted attribution (Phase 3F). True when the row was parsed
    # from a news headline via regex, False/missing when it came from
    # yfinance's structured upgrades_downgrades table.
    from_news: bool = False
    source_link: str | None = None
    source_title: str | None = None


class CompanyProfileOut(BaseModel):
    """Identity / "anagrafica" extracted from yfinance Ticker.info — see
    `services.stock_fundamentals_service.CompanyProfile` docstring."""
    long_business_summary: str | None = None
    website: str | None = None
    employees: int | None = None
    city: str | None = None
    country: str | None = None
    ceo: str | None = None
    founded: int | None = None


class FundamentalsOut(BaseModel):
    ticker: str
    annual: list[FundamentalsAnnualOut] = []
    quarterly: list[FundamentalsQuarterlyOut] = []
    earnings: list[FundamentalsEarningsOut] = []
    next_earnings_date: str | None = None
    # When the next earnings is released relative to the trading session.
    # "pre" -> sole icon (released before market open),
    # "after" -> luna icon (released after market close),
    # None -> no icon (mid-session release, non-US country, or unknown).
    # Computed via earnings_session_timing.classify_session_timing.
    next_earnings_when: Literal["pre", "after"] | None = None
    next_eps_estimate: float | None = None
    next_revenue_estimate: float | None = None
    micro: MicroDataOut = MicroDataOut()
    profile: CompanyProfileOut = CompanyProfileOut()
    insiders: list[InsiderTransactionOut] = []
    analyst_ratings: list[AnalystRatingOut] = []
    analyst_actions: list[AnalystActionOut] = []
    price_target: AnalystPriceTargetOut = AnalystPriceTargetOut(
        current=None, low=None, mean=None, median=None, high=None
    )
    error: str | None = None


class IndicatorPeriodsOut(BaseModel):
    """Actual periods used to compute the indicator series at the requested
    range. The bundle keys (sma20, sma50, sma200, rsi14) are slot names; the
    real periods adapt to the range so a 1-month chart uses fast windows
    instead of an SMA200 that's almost entirely NaN."""
    sma_fast: int
    sma_mid: int
    sma_slow: int
    rsi: int
    bb_period: int
    bb_k: float
    macd_fast: int
    macd_slow: int
    macd_signal: int


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
    # Default for back-compat when older code paths construct IndicatorSeriesOut
    # without specifying periods. Real responses always include it.
    periods: IndicatorPeriodsOut = IndicatorPeriodsOut(
        sma_fast=20, sma_mid=50, sma_slow=200, rsi=14,
        bb_period=20, bb_k=2.0, macd_fast=12, macd_slow=26, macd_signal=9,
    )


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
    """Snapshot of a rule as it'll fire for this stock at scan time.
    Post-watchlist-removal `source` is always "tier1" but kept on the
    wire so the FE schema doesn't churn."""
    kind: str
    enabled: bool
    params: dict[str, Any]
    source: str = "tier1"


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
    # Server-classified headline sentiment. "neutral" when the
    # classifier finds no decisive bull/bear signal in the title,
    # OR for cached pre-sentiment items (the field defaults to
    # neutral on missing input — old payloads still validate).
    sentiment: Literal["bullish", "neutral", "bearish"] = "neutral"


class StockNewsOut(BaseModel):
    items: list[StockNewsItemOut]
