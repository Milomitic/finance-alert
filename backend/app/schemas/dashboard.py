"""Pydantic schemas for the dashboard summary endpoint."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.alert import AlertOut, ScanStatusOut


class KpiSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alerts_last_24h: int
    alerts_prev_24h: int
    stocks_monitored: int
    indices_count: int
    last_scan: ScanStatusOut | None
    next_scan_at: datetime | None
    next_digest_at: datetime | None


class AlertsByDayPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    count: int
    by_kind: dict[str, int]


class TopStockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stock_id: int
    ticker: str
    name: str | None = None
    alert_count: int
    top_kind: str | None


class AlertsByIndexPointOut(BaseModel):
    """One bar in the dashboard's "Per indice" alert breakdown."""
    model_config = ConfigDict(from_attributes=True)

    index_code: str
    index_name: str
    alert_count: int


class SystemStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduler_running: bool
    scan_alerts_next_run: datetime | None
    send_digest_next_run: datetime | None
    refresh_catalog_next_run: datetime | None
    telegram_configured: bool
    last_digest_sent_at: datetime | None


class DashboardSummaryOut(BaseModel):
    kpis: KpiSummaryOut
    alerts_by_day: list[AlertsByDayPointOut]
    top_stocks_30d: list[TopStockOut]
    alerts_by_index_30d: list[AlertsByIndexPointOut]
    recent_alerts: list[AlertOut]
    system_status: SystemStatusOut


class AnalystActionOut(BaseModel):
    """One recent analyst rating action surfaced on the dashboard
    "Ultime valutazioni analisti" card. Mirrors
    `analyst_actions_feed.AnalystActionFeedItem`."""
    ticker: str
    name: str | None = None
    date: str                       # ISO YYYY-MM-DD
    firm: str
    to_grade: str
    from_grade: str
    action: str                     # up | down | init | main | reit | ...
    current_price_target: float | None = None
    # Same firm's prior target so the dashboard chip can render the
    # delta ("$287 → $296") rather than just the current number.
    prior_price_target: float | None = None
    # yfinance's separate "Raises" | "Lowers" | "Maintains" |
    # "Initiates" axis — informative when paired with a Maintain
    # rating (firm holds the grade but moves the target).
    price_target_action: str | None = None
    from_news: bool = False


class PremarketMoverOut(BaseModel):
    """One US pre-market gainer/loser row."""
    ticker: str
    name: str | None = None
    price: float                    # latest pre-market price
    prev_close: float               # prior regular-session close
    change_pct: float               # (price - prev_close)/prev_close * 100
    volume: int | None = None       # summed pre-market volume (None = n/d)


class PremarketMoversOut(BaseModel):
    """US pre-market top gainers/losers. `available` is the single flag
    the frontend keys on: True only when the US regular market is
    CLOSED and fresh pre-market data exists for the latest session
    (otherwise the card is hidden)."""
    available: bool
    market_open: bool
    as_of: str | None = None        # ISO date of the pre-market session
    computed_at: str | None = None  # ISO datetime of last compute
    refreshing: bool = False
    progress_pct: int = 0
    gainers: list[PremarketMoverOut] = []
    losers: list[PremarketMoverOut] = []
