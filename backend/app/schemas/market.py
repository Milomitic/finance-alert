"""Pydantic schemas for /api/dashboard/market-summary response."""
from datetime import datetime

from pydantic import BaseModel, Field


class MarketGlobalOut(BaseModel):
    stocks_total: int
    stocks_with_data: int
    advancers: int
    decliners: int
    unchanged: int
    avg_change_pct: float
    pct_above_sma200: float
    pct_above_sma50: float
    rsi_oversold_count: int
    rsi_overbought_count: int
    near_52w_high_count: int
    near_52w_low_count: int
    mood: str   # "bullish" | "neutral" | "bearish"


class IndexBreadthOut(BaseModel):
    code: str
    name: str
    n: int
    pct_above_sma200: float | None
    pct_above_sma50: float | None
    rsi_oversold_count: int
    rsi_overbought_count: int
    avg_change_pct: float | None
    total_market_cap: float | None = None
    advancers: int
    decliners: int
    new_52w_highs: int
    new_52w_lows: int
    volume_spikes_count: int


class RsiDistributionOut(BaseModel):
    all: list[int]
    by_index: dict[str, list[int]]


class SectorBreadthOut(BaseModel):
    sector: str
    n_stocks: int
    avg_change_pct: float
    pct_above_sma200: float


class MoverOut(BaseModel):
    ticker: str
    name: str
    index: str | None
    sector: str | None
    change_pct: float | None = None
    change_pct_5d: float | None = None
    change_pct_20d: float | None = None
    last_close: float
    prev_close: float | None
    sparkline: list[float] = []  # last ~30 close prices for the per-row UI sparkline


class VolumeSpikeOut(MoverOut):
    vol_ratio: float


class MoversBlockOut(BaseModel):
    gainers: list[MoverOut]
    losers: list[MoverOut]
    gainers_5d: list[MoverOut] = []
    losers_5d: list[MoverOut] = []
    gainers_20d: list[MoverOut] = []
    losers_20d: list[MoverOut] = []
    volume_spikes: list[VolumeSpikeOut]
    new_52w_high: list[MoverOut]
    new_52w_low: list[MoverOut]


class TreemapLeafOut(BaseModel):
    ticker: str
    index: str | None
    sector: str | None
    market_cap: float
    change_pct: float


class MarketSummaryOut(BaseModel):
    available: bool
    is_stale: bool = False
    reason: str | None = None
    computed_at: datetime | None = None
    scan_run_id: int | None = None
    global_block: MarketGlobalOut | None = Field(default=None, alias="global")
    by_index: list[IndexBreadthOut] = []
    rsi_distribution: RsiDistributionOut | None = None
    sectors: list[SectorBreadthOut] = []
    movers: MoversBlockOut | None = None
    treemap: list[TreemapLeafOut] = []

    model_config = {"populate_by_name": True}
