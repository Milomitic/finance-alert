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
    pct_above_ema200: float
    pct_above_ema50: float
    rsi_oversold_count: int
    rsi_overbought_count: int
    near_52w_high_count: int
    near_52w_low_count: int
    mood: str   # "bullish" | "neutral" | "bearish"


class IndexBreadthOut(BaseModel):
    code: str
    name: str
    n: int
    pct_above_ema200: float | None
    pct_above_ema50: float | None
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
    pct_above_ema200: float


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
    # Secondary context — same fields previously lived only on
    # `TopVolumeOut`. Promoted to the base mover row so the dashboard's
    # "Top movers" card (gainers / losers) can render volume + score
    # columns alongside the % change. Optional everywhere: legacy
    # snapshot payloads without these keys still validate.
    vol_today: int | None = None
    vol_ratio: float | None = None
    composite: float | None = None


class VolumeSpikeOut(MoverOut):
    vol_ratio: float


class TopVolumeOut(MoverOut):
    """Stocks ranked by ABSOLUTE share-volume today (vs `VolumeSpikeOut`
    which ranks by the vol_today/vol_avg_20 multiplier). Powers the
    "Volumi maggiori" dashboard card — the row also carries the
    multiplier (for secondary context) and the latest composite score
    (so the card shows "what's hot + how it's scoring", live)."""
    vol_today: int
    vol_ratio: float | None = None
    composite: float | None = None


class MoversBlockOut(BaseModel):
    gainers: list[MoverOut]
    losers: list[MoverOut]
    gainers_5d: list[MoverOut] = []
    losers_5d: list[MoverOut] = []
    gainers_20d: list[MoverOut] = []
    losers_20d: list[MoverOut] = []
    volume_spikes: list[VolumeSpikeOut]
    # Optional for back-compat with snapshots persisted before the field
    # existed; the lazy migration in `api/market.py` keeps older rows
    # readable, and the next scan repopulates this list.
    top_volume: list[TopVolumeOut] = []
    new_52w_high: list[MoverOut]
    new_52w_low: list[MoverOut]


class TreemapLeafOut(BaseModel):
    ticker: str
    index: str | None
    sector: str | None
    market_cap: float
    change_pct: float
    # Listing-currency close and volume for the screener's Prezzo column.
    # Optional for back-compat with snapshots that pre-date this schema.
    last_close: float | None = None
    currency: str | None = None
    vol_today: int | None = None


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
