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

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MacroObservation, MacroSeries, Stock, StockScore
from app.services import calendar_macros, macro_events_service, stock_fundamentals_service
from app.services.calendar_macros import Importance, MacroEvent
from app.services.earnings_session_timing import classify_session_timing

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
    # Inferred timing relative to the trading session: "pre" (before
    # market open), "after" (after close), or None when we cant infer.
    earnings_when: str | None = None
    # Phase 3G: post-release earnings (mirror of MacroEventDC's
    # actual_value / surprise_pct). Populated when the quarter has
    # already reported; None for upcoming quarters. Sourced from
    # `FundamentalsEarnings` rows in the cached fundamentals payload.
    # Mirrors yfinance's `Ticker.earnings_history`:
    #   eps_reported = the actual EPS reported
    #   surprise_pct = (reported - estimate) / |estimate| * 100
    eps_reported: float | None = None
    surprise_pct: float | None = None


@dataclass
class MacroEventDC:
    """Service-layer macro event. Carries the `kind` discriminator +
    optional FRED-driven insight fields (prev/prior/change_pct/history)
    and Forexfactory-driven consensus fields (expected/actual/surprise).
    Hardcoded events from `calendar_macros._MACRO_EVENTS` leave the
    insight fields as their defaults — the calendar UI then renders the
    chip without the prev/change badges."""
    date: date
    kind: Literal["macro"]
    label: str
    importance: Importance
    region: str
    prev_value: float | None = None
    prev_date: date | None = None
    prior_value: float | None = None
    prior_date: date | None = None
    change_pct: float | None = None
    unit: str | None = None
    history: list[tuple[date, float | None]] = field(default_factory=list)
    release_time: str | None = None
    # Phase 3G: consensus / actual / surprise (sourced via
    # `forexfactory_consensus.consensus_for_label` post-build).
    # `expected_value` is the median analyst forecast as parsed from
    # Forexfactory's free weekly XML; `actual_value` is the post-release
    # value from the same feed (faster than waiting for FRED to publish).
    # `surprise_pct` = (actual - expected) / |expected| * 100, computed
    # at calendar-build time when both inputs are available.
    expected_value: float | None = None
    actual_value: float | None = None
    surprise_pct: float | None = None
    # Backing MacroSeries id — drives the link to /macro/:series_id from
    # the calendar event chip. None when the event came from the
    # hardcoded fallback list AND no MacroSeries with the same `label`
    # exists (the enrichment helper resolves it when one does).
    series_id: int | None = None
    # Publishing organization (e.g. "U.S. Bureau of Labor Statistics").
    # Pulled from MacroSeries.source when the series row exists and the
    # seed script has populated it.
    source: str | None = None


# Region → ISO 4217 currency. Single source of truth for the
# region→currency mapping consumed by the macro detail page header.
# Mirrors the region literal set in `schemas/calendar.MacroEventOut`.
_REGION_CURRENCY: dict[str, str] = {
    "US": "USD",
    "EU": "EUR", "EZ": "EUR",
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR",
    "NL": "EUR", "BE": "EUR", "IE": "EUR",
    "UK": "GBP", "GB": "GBP",
    "JP": "JPY",
    "KR": "KRW",
    "CN": "CNY",
    "HK": "HKD",
    "CH": "CHF",
}


def currency_for_region(region: str | None) -> str | None:
    """Return the ISO 4217 currency code for a region, or None for unknown.

    Used by the API layer to populate `MacroEventOut.currency` without
    duplicating the mapping. The detail-page UI shows it next to the
    flag so the user knows which FX a rate-decision event affects.
    """
    if region is None:
        return None
    return _REGION_CURRENCY.get(region)


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

    Filters hidden countries (CN/JP/KR) — those stocks live in DB only
    to feed dashboard breadth + Asia mood, not to surface as individual
    earnings rows. Single source of truth: `app.core.visibility`.
    """
    from app.core.visibility import visible_country_clause

    rows = db.execute(
        select(Stock, StockScore)
        .join(StockScore, StockScore.stock_id == Stock.id)
        .where(visible_country_clause())
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

    def _make(
        d: date,
        eps_est: float | None,
        rev_est: float | None,
        time_utc: str | None,
        eps_reported: float | None = None,
        surprise_pct: float | None = None,
    ) -> EarningsEvent:
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
            earnings_when=classify_session_timing(time_utc, stock.country),
            eps_reported=eps_reported,
            surprise_pct=surprise_pct,
        )

    out: list[EarningsEvent] = []
    seen: set[date] = set()  # dedupe in case `next` overlaps with `earnings[]`

    # Forward-looking: next_earnings_date — by definition not yet reported
    # so eps_reported / surprise_pct stay None.
    nxt_d = _parse_iso_date(cached.next_earnings_date)
    if nxt_d is not None and date_from <= nxt_d <= date_to:
        out.append(_make(nxt_d, cached.next_eps_estimate, cached.next_revenue_estimate, getattr(cached, "next_earnings_time_utc", None)))
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
        # Past quarters: yfinance gives us eps_reported + surprise_pct.
        # `surprise_pct` is the user-facing field the calendar shows
        # under "Sorpresa" — same axis as macro events. Some legacy
        # rows might lack these (yfinance schema drift) → optional.
        out.append(_make(
            d,
            ep.eps_estimate,
            ep.revenue_estimate,
            getattr(ep, "time_utc", None),
            eps_reported=getattr(ep, "eps_reported", None),
            surprise_pct=getattr(ep, "surprise_pct", None),
        ))
        seen.add(d)

    return out


def _convert_macro(m: MacroEvent) -> MacroEventDC:
    from app.services.calendar_macros import release_time_for
    return MacroEventDC(
        date=m.date,
        kind="macro",
        label=m.label,
        importance=m.importance,
        region=m.region,
        release_time=m.release_time or release_time_for(m.label),
    )


def _enrich_with_fred_value(db: Session, ev: MacroEventDC) -> None:
    """Mutate `ev` in place: when the hardcoded event's `label` matches a
    curated FRED series, attach the latest observation as prev_value and
    populate prior/change_pct/history.

    Called for HARDCODED macros (`calendar_macros._MACRO_EVENTS`) which
    don't have these fields populated by `get_fred_events` (since they
    aren't on a FRED release schedule). Without this, the FOMC rate
    decision card would show "ULTIMO —" even though we have the value
    in DFEDTARU.

    No-op when no matching series exists.
    """
    series = db.execute(
        select(MacroSeries).where(MacroSeries.label == ev.label).limit(1)
    ).scalar_one_or_none()
    if series is None:
        return
    # Carry the series id + source so the calendar chip can deep-link to
    # /macro/:series_id and the detail page knows which org publishes it.
    ev.series_id = series.id
    ev.source = series.source
    # Find the latest observation up to (and including) the event's date.
    # Using <= here so a same-day observation (e.g. DFEDTARU updated on
    # FOMC day) IS attached.
    row = db.execute(
        select(MacroObservation.value, MacroObservation.date)
        .where(
            MacroObservation.series_id == series.id,
            MacroObservation.date <= ev.date,
        )
        .order_by(MacroObservation.date.desc())
        .limit(1)
    ).first()
    if row is None:
        return
    ev.prev_value = row.value
    ev.prev_date = row.date
    ev.unit = series.unit
    # Also attach the observation BEFORE that one as prior_value, +
    # compute Δ% so the existing "Δ vs prec." badge still has data
    # (the UI may still show it for non-FOMC events).
    prior_row = db.execute(
        select(MacroObservation.value, MacroObservation.date)
        .where(
            MacroObservation.series_id == series.id,
            MacroObservation.date < row.date,
        )
        .order_by(MacroObservation.date.desc())
        .limit(1)
    ).first()
    if prior_row is not None:
        ev.prior_value = prior_row.value
        ev.prior_date = prior_row.date
        if prior_row.value not in (None, 0):
            ev.change_pct = ((row.value - prior_row.value) / prior_row.value) * 100
    # Recent history for the inline sparkline.
    history_rows = db.execute(
        select(MacroObservation.date, MacroObservation.value)
        .where(MacroObservation.series_id == series.id)
        .order_by(MacroObservation.date.desc())
        .limit(12)
    ).all()
    ev.history = [(r.date, r.value) for r in reversed(history_rows)]


def _enrich_with_forexfactory(ev: MacroEventDC) -> None:
    """Mutate `ev` in place: attach `expected_value`, `actual_value`,
    `surprise_pct` (and as backup `prev_value`) from Forexfactory's
    free weekly XML feed when a consensus is available for this
    label/date pair.

    No-op when:
    - The label isn't in `forexfactory_consensus._FF_LABEL_MAP` (we
      don't track every label — only the major US/EU/UK/JP events
      where the feed reliably publishes consensus).
    - No matching event in this week's XML.
    - Both forecast and actual are empty in the feed.

    `prev_value` fallback: for non-US events we don't have a FRED
    `MacroSeries` to source the previous reading from, so we lift
    Forexfactory's `previous` field. This lets the UI render its
    "Attuale / Previsto / Precedente" strip for UK/EU/JP releases —
    without it `hasInsight` is false and the strip never appears.
    """
    from app.services import forexfactory_consensus as ff
    ff_event = ff.consensus_for_label(ev.label, ev.date)
    if ff_event is None:
        return
    expected = ff.parse_numeric(ff_event.forecast)
    actual = ff.parse_numeric(ff_event.actual)
    previous = ff.parse_numeric(ff_event.previous)
    if expected is not None:
        ev.expected_value = expected
    if actual is not None:
        ev.actual_value = actual
    # Only fall back to FF's `previous` when FRED hasn't already
    # populated `prev_value` (FRED is authoritative for the few series
    # both sources cover, e.g. US CPI).
    if ev.prev_value is None and previous is not None:
        ev.prev_value = previous
    if expected is not None and actual is not None and expected != 0:
        # Sign-preserving relative surprise. Magnitudes work cleanly
        # for non-zero expected; "expected=0" cases (rare) get null
        # because dividing by zero would fly to ±∞.
        ev.surprise_pct = ((actual - expected) / abs(expected)) * 100


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

        # FRED-driven events first — they carry insight fields
        # (prev/prior/change_pct/history). Each event is keyed by
        # (label, date) so we can dedupe against the hardcoded list
        # below without showing the same release twice.
        fred_events = macro_events_service.get_fred_events(
            db, date_from, date_to,
        )
        seen_keys: set[tuple[str, date]] = set()
        for fe in fred_events:
            if importance_filter is not None and fe.importance not in importance_filter:
                continue
            seen_keys.add((fe.label, fe.date))
            from app.services.calendar_macros import release_time_for
            events.append(
                MacroEventDC(
                    date=fe.date,
                    kind="macro",
                    label=fe.label,
                    importance=fe.importance,  # type: ignore[arg-type]
                    region=fe.region,
                    prev_value=fe.prev_value,
                    prev_date=fe.prev_date,
                    prior_value=fe.prior_value,
                    prior_date=fe.prior_date,
                    change_pct=fe.change_pct,
                    unit=fe.unit,
                    history=fe.history,
                    release_time=release_time_for(fe.label),
                    series_id=fe.series_id,
                    source=fe.source,
                )
            )

        # Hardcoded fallback fills regions FRED doesn't reliably cover
        # (BoE, BoJ, BoK, PBoC, ZEW, IFO, …) AND series whose curated
        # release_id is None (FOMC: pulled daily, scheduled hardcoded).
        # Skip any (label, date) already produced by FRED above to avoid
        # duplicates. Each hardcoded event gets a FRED-value lookup so
        # the card shows ULTIMO even though no FRED release row exists.
        macros = calendar_macros.get_macro_events(
            date_from, date_to, importance_filter,
        )
        for m in macros:
            if (m.label, m.date) in seen_keys:
                continue
            ev = _convert_macro(m)
            _enrich_with_fred_value(db, ev)
            events.append(ev)

        # Forexfactory consensus / actual / surprise post-pass — applied
        # to BOTH FRED-driven and hardcoded macros so every macro event
        # has expected/surprise when a free consensus is available.
        # The lookup is in-memory cached for 30 min so this is cheap
        # even for a 2-week window with ~50 macro events.
        for ev in events:
            if isinstance(ev, MacroEventDC):
                _enrich_with_forexfactory(ev)

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
