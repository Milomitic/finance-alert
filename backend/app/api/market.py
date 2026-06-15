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
    # Globex so they're our after-hours signal. Default False = the row
    # shows the cash quote (most rows: commodities, crypto, indices
    # during regular hours, and indices without a paired futures pair).
    using_futures: bool = False
    # The yfinance symbol the DISPLAYED quote actually came from — the
    # futures contract when `using_futures`, else the cash symbol. The
    # dashboard links the row's detail page to THIS so the detail shows
    # the same instrument/price the card shows (no more cash↔futures
    # price mismatch when the cash market is closed).
    quote_symbol: str = ""
    # True when the displayed price is updating in REAL TIME right now —
    # category-aware (crypto 24/7; futures on the Globex ~23h session;
    # cash indices during their exchange hours). Drives the live dot.
    is_live: bool = False


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


def _globex_session_live(now: datetime) -> bool:
    """Approximate whether the CME Globex futures session is open at `now`
    (UTC). Globex runs Sun 22:00 → Fri 22:00 UTC with a ~60-min daily break
    around 21:00-22:00 UTC. Good enough for a "is this price live" dot — not
    an order-routing calendar (holidays not modeled)."""
    wd = now.weekday()  # Mon=0 .. Sun=6
    mins = now.hour * 60 + now.minute
    if wd == 5:                       # Saturday — closed all day
        return False
    if wd == 4 and mins >= 22 * 60:   # Friday after 22:00 UTC
        return False
    if wd == 6 and mins < 22 * 60:    # Sunday before 22:00 UTC (reopen)
        return False
    if 21 * 60 <= mins < 22 * 60:     # daily maintenance break
        return False
    return True


def _quote_is_live(category: str, using_futures: bool, cash_q, now: datetime) -> bool:
    """Is the DISPLAYED price updating in real time right now? Category-aware:
    crypto trades 24/7; commodities (=F) and index futures follow the Globex
    session; a cash index is live only during its exchange's regular hours
    (the quote's own market_state)."""
    if category == "crypto":
        return True
    if category == "commodity" or using_futures:
        return _globex_session_live(now)
    return bool(cash_q and cash_q.market_state == "OPEN" and cash_q.error is None)


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
    now_utc = datetime.now(UTC)
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

        quote_symbol = futures_symbol if (use_futures and futures_symbol) else symbol
        is_live = (
            _quote_is_live(category, use_futures, cash_q, now_utc)
            and effective_q is not None
            and effective_q.price is not None
            and effective_q.error is None
        )
        out.append(LiveAsset(
            symbol=symbol,
            name=name,
            category=category,
            flag=flag,
            quote=LiveQuoteOut(**effective_q.__dict__) if effective_q else None,
            history=histories.get(symbol),
            using_futures=use_futures,
            quote_symbol=quote_symbol,
            is_live=is_live,
        ))
    return LiveAssetsOut(assets=out)


def _migrate_sma_keys_in_place(payload: dict) -> None:
    """Lazy SMA→EMA key migration for snapshots persisted before the
    May 2026 indicator rename.

    The market_snapshot row stores a serialised JSON blob whose keys
    used to be `pct_above_sma200` / `pct_above_sma50`. The new
    Pydantic schema expects `pct_above_ema200` / `pct_above_ema50`
    (matching the math change from SMA to EMA — see
    `services/market_stats_service.py` for context).

    Rather than force a full scan to regenerate the snapshot — which
    can take 5+ minutes and is the user's lived "broken dashboard"
    experience — we rewrite the keys in-place at read time. The next
    scan's `recompute_snapshot` will persist the new keys directly,
    making this migration self-healing on first scan after deploy.

    Mutates `payload` in place. Safe to call on a payload that already
    has the new keys — the rename is a no-op when the old key is
    absent.
    """
    OLD_TO_NEW = {
        "pct_above_sma200": "pct_above_ema200",
        "pct_above_sma50": "pct_above_ema50",
    }

    def _rename(d: dict) -> None:
        for old, new in OLD_TO_NEW.items():
            if old in d and new not in d:
                d[new] = d.pop(old)
            elif old in d:
                # Both keys present (shouldn't happen in practice) — keep
                # the new value, drop the old.
                d.pop(old, None)

    if isinstance(payload.get("global"), dict):
        _rename(payload["global"])
    for row in payload.get("by_index") or []:
        if isinstance(row, dict):
            _rename(row)
    for row in payload.get("sectors") or []:
        if isinstance(row, dict):
            _rename(row)


@router.get("/market-summary", response_model=MarketSummaryOut, response_model_by_alias=True)
def get_market_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MarketSummaryOut:
    snap = market_stats_service.get_latest_snapshot(db)
    if snap is None:
        return MarketSummaryOut(available=False, reason="no_scan_yet")

    payload = json.loads(snap.payload)
    # Migrate legacy SMA-named keys before Pydantic validation. Cheap
    # in-place dict-rename, self-healing on the next scan.
    _migrate_sma_keys_in_place(payload)
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
