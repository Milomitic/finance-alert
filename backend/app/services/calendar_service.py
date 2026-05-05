"""Calendar aggregator: earnings (per-stock from fundamentals cache) + macros.

Inputs come from two distinct sources:
- Earnings: walk the catalog, but only stocks that already have a computed
  `StockScore` row — this caps the fan-out to the ~50-300 stocks the user
  has shown interest in (rather than all 1100+). For each such stock, read
  the cached fundamentals and pull `next_earnings_date` + every historical
  `earnings[].date` that falls in [from, to].
- Macros: hardcoded list filtered by date + importance.

Critical constraint (per docs/calendar-page.md): the aggregator MUST NOT
trigger fundamentals network calls. We read `stock_fundamentals_service._CACHE`
directly — empty cache for a stock = silently skipped (the next scan's
recompute_all will warm it).

Output is a single sorted list of typed events. Sort key is (date asc,
earnings-before-macros, importance desc within a day).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock, StockScore
from app.services import calendar_macros, stock_fundamentals_service
from app.services.calendar_macros import Importance, MacroEvent

# Sort order — macros first per UX spec (V2): macros are scarcer + higher
# signal at a glance than the long tail of earnings releases on any given
# day, so they should anchor the cell preview. Within macros, importance
# desc; within earnings, market_cap desc so the largest names show first
# when chips are space-capped in the cell.


# ---------------------------------------------------------------------------
# Public dataclasses returned by `get_events`. The API layer maps these onto
# Pydantic schemas. Keeping them as plain dataclasses lets test code assert
# fields without going through the FastAPI / TestClient round-trip.
# ---------------------------------------------------------------------------

@dataclass
class EarningsEvent:
    date: date
    kind: Literal["earnings"]
    ticker: str
    name: str
    eps_estimate: float | None
    revenue_estimate: float | None
    sector: str | None
    market_cap: int | None
    # Extras used by the right-pane stock list. These come from the
    # fundamentals cache (`MicroData`) + the `StockScore` table joined on
    # the catalog walk. None when not yet computed/scored — UI shows "—".
    forward_pe: float | None = None
    earnings_growth: float | None = None       # YoY EPS growth, fraction
    composite_score: float | None = None       # 0-100 composite score
    risk_tier: str | None = None               # "conservative"/"moderate"/"aggressive"


@dataclass
class MacroEventDC:
    """Service-layer macro event. Mirrors `calendar_macros.MacroEvent` but
    carries the `kind` discriminator so the API can serialize uniformly."""
    date: date
    kind: Literal["macro"]
    label: str
    importance: Importance
    region: str


CalendarEvent = EarningsEvent | MacroEventDC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_KINDS: frozenset[str] = frozenset({"earnings", "macro"})
_VALID_IMPORTANCE: frozenset[str] = frozenset({"high", "medium", "low"})


def _parse_iso_date(s: str | None) -> date | None:
    """yfinance dates come through as 'YYYY-MM-DD' or sometimes
    'YYYY-MM-DD HH:MM:SS+TZ'. We only need the date part."""
    if not s:
        return None
    try:
        # Cheap fast path
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _scored_stocks(db: Session) -> list[tuple[Stock, StockScore]]:
    """Stocks that have a corresponding StockScore row, paired with the score.

    Returning the StockScore alongside lets `_earnings_for_stock` populate the
    new composite_score / risk_tier fields on EarningsEvent without a second
    query per stock. Catalog has duplicate ticker rows (CLAUDE.md) — the JOIN
    naturally picks only the row a score is attached to.
    """
    rows = db.execute(
        select(Stock, StockScore).join(StockScore, StockScore.stock_id == Stock.id)
    ).all()
    return [(stock, score) for stock, score in rows]


def _earnings_for_stock(
    stock: Stock, score: StockScore, date_from: date, date_to: date,
) -> list[EarningsEvent]:
    """Pull every earnings event for `stock` whose date falls in the window.

    Reads `_CACHE` directly — does NOT call `get_fundamentals` so we never
    trigger a yfinance roundtrip from the calendar path. If the cache is
    cold for this ticker we return [] silently.

    A given stock can appear MULTIPLE times in the output if it had a
    historical print AND has an upcoming print AND both fall in the window.
    Practically the window is ≤ 366 days so at most ~5 entries per stock.
    """
    cached = stock_fundamentals_service._CACHE.get(stock.ticker)
    if cached is None:
        return []

    # These fields don't change per event date, so compute once at the top.
    forward_pe = cached.micro.forward_pe if cached.micro else None
    earnings_growth = cached.micro.earnings_growth if cached.micro else None

    def _make(d: date, eps_est: float | None, rev_est: float | None) -> EarningsEvent:
        return EarningsEvent(
            date=d,
            kind="earnings",
            ticker=stock.ticker,
            name=stock.name,
            eps_estimate=eps_est,
            revenue_estimate=rev_est,
            sector=stock.sector,
            market_cap=stock.market_cap,
            forward_pe=forward_pe,
            earnings_growth=earnings_growth,
            composite_score=score.composite if score else None,
            risk_tier=score.risk_tier if score else None,
        )

    out: list[EarningsEvent] = []
    seen: set[date] = set()  # dedupe in case `next` overlaps with `earnings[]`

    # Forward-looking: next_earnings_date
    nxt_d = _parse_iso_date(cached.next_earnings_date)
    if nxt_d is not None and date_from <= nxt_d <= date_to:
        out.append(_make(nxt_d, cached.next_eps_estimate, cached.next_revenue_estimate))
        seen.add(nxt_d)

    # Historical (and any forward dates yfinance puts in earnings[] without
    # a reported value): walk earnings[] and admit anything in window we
    # haven't already added via next_earnings_date.
    for ep in cached.earnings:
        d = _parse_iso_date(ep.date)
        if d is None or d in seen:
            continue
        if not (date_from <= d <= date_to):
            continue
        out.append(_make(d, ep.eps_estimate, ep.revenue_estimate))
        seen.add(d)

    return out


def _convert_macro(m: MacroEvent) -> MacroEventDC:
    return MacroEventDC(
        date=m.date,
        kind="macro",
        label=m.label,
        importance=m.importance,
        region=m.region,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_events(
    db: Session,
    date_from: date,
    date_to: date,
    *,
    kinds: set[str] | None = None,
    importance: set[str] | None = None,
) -> list[CalendarEvent]:
    """Aggregate earnings + macros for [date_from, date_to].

    `kinds`: None or {"earnings","macro"} returns both. {"earnings"} skips
    the macro list, {"macro"} skips the earnings walk.

    `importance`: filters macros only — earnings are always included
    regardless. None means no importance filter (all macros pass).

    Returns a flat sorted list. Sort key (within the result):
      (date asc, kind: earnings before macros, importance: high → low).

    The caller is responsible for date validation (from <= to, range cap);
    we trust the inputs at this layer.
    """
    if kinds is None:
        kinds = {"earnings", "macro"}

    events: list[CalendarEvent] = []

    if "earnings" in kinds:
        for stock, score in _scored_stocks(db):
            events.extend(_earnings_for_stock(stock, score, date_from, date_to))

    if "macro" in kinds:
        importance_filter: set[Importance] | None
        if importance is None:
            importance_filter = None
        else:
            # Already validated by the caller; cast to the Literal set.
            importance_filter = set(importance)  # type: ignore[arg-type]
        macros = calendar_macros.get_macro_events(
            date_from, date_to, importance_filter,
        )
        events.extend(_convert_macro(m) for m in macros)

    # Final sort:
    #   primary: date asc
    #   secondary: kind — MACRO first (0) before earnings (1). Macros are
    #     scarcer and more "anchoring" per UX spec — they should top the
    #     cell preview so the user sees "FOMC, then earnings" hierarchy.
    #   tertiary: within macros, importance desc → high(0), medium(1), low(2);
    #             within earnings, market_cap desc so the largest names show
    #             first when chips are space-capped in the cell preview.
    importance_rank = {"high": 0, "medium": 1, "low": 2}
    def _sort_key(e: CalendarEvent) -> tuple[date, int, int, str]:
        if isinstance(e, EarningsEvent):
            # market_cap desc encoded as negative → smaller sort key for larger cap.
            mc = -(e.market_cap or 0)
            return (e.date, 1, mc, e.ticker)
        return (e.date, 0, importance_rank.get(e.importance, 99), e.label)

    events.sort(key=_sort_key)
    return events


__all__ = [
    "EarningsEvent",
    "MacroEventDC",
    "CalendarEvent",
    "get_events",
]
