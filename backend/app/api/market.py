"""Dashboard market endpoints:
  GET /api/dashboard/market-summary — pre-computed snapshot (existing)
  GET /api/dashboard/live-assets    — curated live assets panel (new)
"""
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.market import MarketSummaryOut
from app.schemas.stock_detail import LiveQuoteOut
from app.services import (
    live_quote_service,
    live_sparkline_service,
    market_stats_service,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

STALE_THRESHOLD = timedelta(hours=24)


# ─── Live assets panel ─────────────────────────────────────────────────────
# Hardcoded curated list rendered at the top of the dashboard. yfinance
# symbols are used directly: caret-prefixed for indices (^GSPC), futures
# suffixes for commodities (`=F`), `-USD` pairs for crypto. The catalog
# membership check that the regular `/api/stocks/quotes` endpoint does
# is bypassed here — these are NOT stocks the user trades, they're
# market context shown for situational awareness.

class LiveAsset(BaseModel):
    """One row of the live assets panel."""
    symbol: str           # yfinance symbol (^GSPC, BTC-USD, GC=F, ...)
    name: str             # human label ("S&P 500", "Bitcoin", "Gold")
    category: str         # "index" | "commodity" | "crypto"
    flag: str | None = None  # 2-letter region code, lowercase ("us", "jp", "it"); None for global assets
    quote: LiveQuoteOut | None = None  # null when fetch failed / breaker open
    history: list[float] | None = None  # ~30 trailing daily closes for the sparkline; None on fetch failure


class LiveAssetsOut(BaseModel):
    assets: list[LiveAsset]


# Curated panel composition. Order matters — it's the rendering order.
# Mix of US, EU, Asia indices + the half-dozen commodities and crypto
# pairs a finance-news headline references on a typical morning.
LIVE_ASSET_DEFINITIONS: list[tuple[str, str, str, str | None]] = [
    # symbol,         name,                 category,    flag
    ("^GSPC",        "S&P 500",            "index",     "us"),
    ("^IXIC",        "Nasdaq Composite",   "index",     "us"),
    ("^DJI",         "Dow Jones",          "index",     "us"),
    ("^N225",        "Nikkei 225",         "index",     "jp"),
    ("^STOXX50E",    "Euro Stoxx 50",      "index",     "eu"),
    ("FTSEMIB.MI",   "FTSE MIB",           "index",     "it"),
    ("^HSI",         "Hang Seng",          "index",     "hk"),
    # CSI 300 stays in the dashboard even though Chinese-mainland
    # stocks were removed from the catalog (per user) — they still
    # want to track the headline Chinese index's daily move.
    ("000300.SS",    "CSI 300",            "index",     "cn"),
    ("GC=F",         "Oro (futures)",      "commodity", None),
    ("SI=F",         "Argento (futures)",  "commodity", None),
    ("CL=F",         "Petrolio WTI",       "commodity", None),
    ("NG=F",         "Gas naturale",       "commodity", None),
    ("BTC-USD",      "Bitcoin",            "crypto",    None),
    ("ETH-USD",      "Ethereum",           "crypto",    None),
]


@router.get("/live-assets", response_model=LiveAssetsOut)
def get_live_assets(_user: User = Depends(get_current_user)) -> LiveAssetsOut:
    """Curated live snapshots of indices / commodities / crypto for the
    dashboard panel. Polled by the frontend on a 15s cadence; the live
    quote service caches each symbol for 10s so concurrent tabs share
    a single yfinance call.

    Bypasses the `Stock` catalog membership filter that
    `/api/stocks/quotes` applies — these symbols are intentionally NOT
    in the catalog (they aren't tradeable equities the user follows).
    """
    symbols = [d[0] for d in LIVE_ASSET_DEFINITIONS]
    quotes = live_quote_service.get_quotes_batch(symbols)
    # Sparkline history has its own 15-min TTL cache; it returns
    # already-cached arrays cheaply on most calls.
    histories = live_sparkline_service.get_sparklines(symbols)
    out: list[LiveAsset] = []
    for symbol, name, category, flag in LIVE_ASSET_DEFINITIONS:
        q = quotes.get(symbol)
        # `get_quote` always returns a LiveQuote, but `error` may be set
        # and `price` may be None. We pass it through; the frontend
        # renders "—" gracefully in those cases.
        out.append(LiveAsset(
            symbol=symbol,
            name=name,
            category=category,
            flag=flag,
            quote=LiveQuoteOut(**q.__dict__) if q else None,
            history=histories.get(symbol),
        ))
    return LiveAssetsOut(assets=out)


@router.get("/market-summary", response_model=MarketSummaryOut, response_model_by_alias=True)
def get_market_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MarketSummaryOut:
    snap = market_stats_service.get_latest_snapshot(db)
    if snap is None:
        return MarketSummaryOut(available=False, reason="no_scan_yet")

    payload = json.loads(snap.payload)
    computed_at_utc = snap.computed_at.replace(tzinfo=UTC) if snap.computed_at.tzinfo is None else snap.computed_at
    is_stale = (datetime.now(UTC) - computed_at_utc) > STALE_THRESHOLD

    return MarketSummaryOut(
        available=True,
        is_stale=is_stale,
        computed_at=snap.computed_at,
        scan_run_id=snap.scan_run_id,
        **{"global": payload["global"]},
        by_index=payload["by_index"],
        rsi_distribution=payload["rsi_distribution"],
        sectors=payload["sectors"],
        movers=payload["movers"],
        treemap=payload["treemap"],
    )
