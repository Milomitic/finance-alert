"""Stock response schemas."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticker: str
    exchange: str
    name: str
    sector: str | None
    industry: str | None
    country: str | None
    currency: str | None
    market_cap: int | None
    # "equity" | "etf" — lets the UI badge ETF/ETN rows (they carry no
    # fundamental Qualità score by design). Defaulted for back-compat with
    # constructors that predate the column.
    instrument_type: str = "equity"


class StockScoreRefOut(BaseModel):
    """Compact score data joined into the screener row. Either both fields
    are populated (stock has a computed score) or both are None (unscored).
    Mirrors `StockScoreRef` in the service layer."""
    composite: float | None = None
    risk_tier: Literal["conservative", "moderate", "aggressive"] | None = None
    profitability: float | None = None
    sustainability: float | None = None
    growth: float | None = None
    value: float | None = None
    momentum: float | None = None
    sentiment: float | None = None


class TechnicalScoreRefOut(BaseModel):
    """Continuous technical score on the screener row. All None when the stock
    has no technical score yet. Mirrors StockTechRef in the service layer."""
    composite: float | None = None
    trend: float | None = None
    momentum: float | None = None
    structure: float | None = None
    volume: float | None = None
    rel_strength: float | None = None
    signals: float | None = None
    posture: str | None = None


class StockMetricsRefOut(BaseModel):
    """EOD price/volume metrics on the screener row (from stock_metrics). All
    None when the stock has no metrics row yet. Mirrors StockMetricsRef."""
    last_close: float | None = None
    change_pct: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    high_252: float | None = None
    low_252: float | None = None
    vol_ratio: float | None = None


class StockSearchItemOut(BaseModel):
    """A row in the screener result. Carries the Stock anagrafica + the
    optional score join. Splitting score into a sub-object (vs flattening
    onto StockOut) keeps the bare `StockOut` lean for endpoints that don't
    need scoring data (`GET /api/stocks/{ticker}` etc.)."""
    stock: StockOut
    score: StockScoreRefOut
    technical: TechnicalScoreRefOut = TechnicalScoreRefOut()
    metrics: StockMetricsRefOut = StockMetricsRefOut()


class StockSearchOut(BaseModel):
    items: list[StockSearchItemOut]
    total: int
    has_more: bool
    # As-of of the last stock_metrics refresh (one value for the whole
    # table — every row of a refresh shares a computed_at). None when no
    # scan has persisted metrics yet. UTC, ISO-serialized.
    metrics_computed_at: datetime | None = None


class IndexOptionOut(BaseModel):
    code: str
    name: str


class FilterOptionsOut(BaseModel):
    exchanges: list[str]
    sectors: list[str]
    industries: list[str]
    countries: list[str]
    indices: list[IndexOptionOut]
