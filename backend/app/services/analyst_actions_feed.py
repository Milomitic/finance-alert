"""Aggregate recent analyst rating actions across the stock pool.

The dashboard's "Ultime valutazioni analisti" card needs a single
flattened feed of the most recent upgrades/downgrades/initiations
across every stock we have data for — ranked newest-first.

Why read from the L1 fundamentals cache instead of the DB:
- `analyst_actions` is part of the Fundamentals dataclass, persisted
  in the L2 `fetch_cache` table as a JSON blob, NOT as queryable rows.
  There is no `analyst_actions` table to `SELECT ... ORDER BY date`.
- `stock_fundamentals_service._CACHE` (L1) holds the already-hydrated
  Fundamentals objects for every ticker fetched this process — and the
  app hydrates L1 from L2 at startup (`_hydrate_fetch_caches`). So the
  in-memory dict is a complete-enough, microsecond-fast source.
- Building this from the DB would mean JSON-decoding every fetch_cache
  row on every dashboard load. The L1 read is essentially free.

Freshness gate: yfinance's `upgrades_downgrades` table carries actions
going back months. The card is about "what just came out", so we only
surface actions within `_MAX_AGE_DAYS` and cap the list.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

# Only show actions from roughly the last quarter — older grade changes
# are stale signal for a "latest ratings" card.
_MAX_AGE_DAYS = 90
# Hard cap so the card render stays cheap and scannable.
_MAX_ITEMS = 40


@dataclass
class AnalystActionFeedItem:
    ticker: str
    name: str
    date: str            # ISO YYYY-MM-DD
    firm: str
    to_grade: str
    from_grade: str
    action: str          # "up" | "down" | "init" | "main" | "reit" | ...
    current_price_target: float | None
    from_news: bool


def _parse_iso(d: str) -> date | None:
    try:
        return date.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return None


def recent_actions(limit: int = _MAX_ITEMS) -> list[AnalystActionFeedItem]:
    """Flatten + rank the most recent analyst actions across the pool.

    Reads `stock_fundamentals_service._CACHE` (L1). Returns at most
    `limit` items, newest first, filtered to the last `_MAX_AGE_DAYS`.
    """
    # Lazy import: avoid a heavy import at module load + keep the
    # dependency direction one-way (services → this, not this → services
    # at import time).
    from app.services import stock_fundamentals_service as sfs

    cutoff = (datetime.now(UTC).date() - timedelta(days=_MAX_AGE_DAYS))
    out: list[tuple[date, AnalystActionFeedItem]] = []

    # Snapshot the cache values; _CACHE may be mutated concurrently by a
    # fetch on another thread. dict.values() over a list copy is safe.
    for fund in list(sfs._CACHE.values()):
        actions = getattr(fund, "analyst_actions", None) or []
        if not actions:
            continue
        ticker = getattr(fund, "ticker", "") or ""
        # Fundamentals carries only the ticker — the company name lives
        # in the Stock DB table. We leave `name == ticker` here and let
        # the API endpoint enrich names via a single batched query (it
        # has the DB session; this service stays cache-only).
        name = ticker
        for a in actions:
            d = _parse_iso(getattr(a, "date", "") or "")
            if d is None or d < cutoff:
                continue
            out.append((
                d,
                AnalystActionFeedItem(
                    ticker=ticker,
                    name=name,
                    date=d.isoformat(),
                    firm=getattr(a, "firm", "") or "",
                    to_grade=getattr(a, "to_grade", "") or "",
                    from_grade=getattr(a, "from_grade", "") or "",
                    action=getattr(a, "action", "") or "",
                    current_price_target=getattr(a, "current_price_target", None),
                    from_news=bool(getattr(a, "from_news", False)),
                ),
            ))

    # Newest first; tiebreak by ticker for a stable order.
    out.sort(key=lambda t: (t[0], t[1].ticker), reverse=True)
    return [item for _, item in out[:limit]]
