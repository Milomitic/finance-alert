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
    # When True, the `quote` field is sourced from the index's E-mini
    # futures contract (e.g. ES=F for ^GSPC) because the cash market
    # was closed at request time. Futures trade nearly 24h on CME
    # Globex so they're our after-hours signal. Frontend renders a
    # small "FUT" badge so the user knows the price isn't the cash
    # close anymore. Default False = the row shows the cash quote
    # (most rows: commodities, crypto, indices during regular hours,
    # and indices without a paired futures symbol).
    using_futures: bool = False


class LiveAssetsOut(BaseModel):
    assets: list[LiveAsset]


# Curated panel composition. Order matters — it's the rendering order.
# Mix of US, EU, Asia indices + the half-dozen commodities and crypto
# pairs a finance-news headline references on a typical morning.
#
# Tuple shape: (symbol, name, category, flag, futures_symbol)
#
# `futures_symbol` is the yfinance ticker for the index's E-mini
# futures contract — used as a fallback price source when the cash
# market is closed. CME Globex futures trade ~23h/day (Sun 23:00 UTC
# - Fri 22:00 UTC with a 1h pause), giving us continuous after-hours
# coverage. Set to None when no liquid futures contract exists on
# yfinance (FTSE MIB, CSI 300, Hang Seng cash quotes have no
# yfinance-accessible futures pair) or when the row IS itself a
# futures contract (commodities) or 24h asset (crypto).
LIVE_ASSET_DEFINITIONS: list[tuple[str, str, str, str | None, str | None]] = [
    # symbol,         name,                 category,    flag, futures_symbol
    ("^GSPC",        "S&P 500",            "index",     "us", "ES=F"),
    ("^IXIC",        "Nasdaq Composite",   "index",     "us", "NQ=F"),
    ("^DJI",         "Dow Jones",          "index",     "us", "YM=F"),
    ("^N225",        "Nikkei 225",         "index",     "jp", "NKD=F"),
    ("^STOXX50E",    "Euro Stoxx 50",      "index",     "eu", None),
    ("FTSEMIB.MI",   "FTSE MIB",           "index",     "it", None),
    ("^HSI",         "Hang Seng",          "index",     "hk", None),
    # CSI 300 stays in the dashboard even though Chinese-mainland
    # stocks were removed from the catalog (per user) — they still
    # want to track the headline Chinese index's daily move.
    ("000300.SS",    "CSI 300",            "index",     "cn", None),
    ("GC=F",         "Oro (futures)",      "commodity", None, None),
    ("SI=F",         "Argento (futures)",  "commodity", None, None),
    ("CL=F",         "Petrolio WTI",       "commodity", None, None),
    ("NG=F",         "Gas naturale",       "commodity", None, None),
    ("BTC-USD",      "Bitcoin",            "crypto",    None, None),
    ("ETH-USD",      "Ethereum",           "crypto",    None, None),
]


@router.get("/live-assets", response_model=LiveAssetsOut)
def get_live_assets(_user: User = Depends(get_current_user)) -> LiveAssetsOut:
    """Curated live snapshots of indices / commodities / crypto for the
    dashboard panel. Polled by the frontend on a 15s cadence; the live
    quote service caches each symbol for 10s so concurrent tabs share
    a single yfinance call.

    After-hours futures fallback: rows that have a paired futures
    symbol (ES=F for ^GSPC, NQ=F for ^IXIC, etc.) get a SECOND quote
    fetched in the same batch. When the cash market is CLOSED at
    request time AND the futures quote has a valid price, we swap the
    `quote` field with the futures one and set `using_futures=True`.
    The frontend uses the flag to render a small "FUT" badge so the
    user understands the price source changed.

    Bypasses the `Stock` catalog membership filter that
    `/api/stocks/quotes` applies — these symbols are intentionally NOT
    in the catalog (they aren't tradeable equities the user follows).
    """
    # Single batch call for cash + futures symbols — minimizes the
    # roundtrip to live_quote_service.get_quotes_batch which itself
    # fans out to yfinance.
    cash_symbols = [d[0] for d in LIVE_ASSET_DEFINITIONS]
    futures_symbols = [d[4] for d in LIVE_ASSET_DEFINITIONS if d[4]]
    all_symbols = cash_symbols + futures_symbols
    quotes = live_quote_service.get_quotes_batch(all_symbols)
    # Sparkline history has its own 15-min TTL cache; it returns
    # already-cached arrays cheaply on most calls. We only render the
    # cash sparkline (the futures' history would have a tiny basis
    # offset from cash so mixing them in one chart would show
    # phantom jumps at the cash↔futures swap-over).
    histories = live_sparkline_service.get_sparklines(cash_symbols)
    out: list[LiveAsset] = []
    for symbol, name, category, flag, futures_symbol in LIVE_ASSET_DEFINITIONS:
        cash_q = quotes.get(symbol)
        # Decide: use cash or futures?
        # - If cash market is OPEN (or the row is a 24h commodity / crypto
        #   row that we don't have a futures pair for) → use cash.
        # - If cash market is CLOSED AND futures quote has a price →
        #   swap to futures, set using_futures.
        use_futures = False
        effective_q = cash_q
        if futures_symbol and cash_q and cash_q.market_state != "OPEN":
            futures_q = quotes.get(futures_symbol)
            if futures_q and futures_q.price is not None and futures_q.error is None:
                effective_q = futures_q
                use_futures = True

        out.append(LiveAsset(
            symbol=symbol,
            name=name,
            category=category,
            flag=flag,
            quote=LiveQuoteOut(**effective_q.__dict__) if effective_q else None,
            history=histories.get(symbol),
            using_futures=use_futures,
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
