"""Single source of truth for "stocks hidden from user-facing surfaces".

These countries are seeded into the catalog so they contribute to the
dashboard breadth row + Asia market-mood aggregation in
`market_stats_service._load_metrics`, but the user explicitly opted
out of trading / tracking them individually:

- Search / autocomplete
- Screener
- Stock detail page (deep links return 404)
- Alert generation (scan service skips them)
- Movers list (gainers / losers)
- Treemap
- Sectors heatmap
- Top picks score-rank lists

The metrics pipeline (`_load_metrics`) intentionally does NOT consult
this set — that's how the breadth + mood signal still see the hidden
stocks, while every consumer that exposes individual rows to the user
filters them.

Adding/removing a country here changes the visibility cutoff for the
whole app from one place.
"""
from __future__ import annotations

from sqlalchemy import or_

from app.models import Stock

# ISO-2 country codes whose stocks are catalog-only (metrics) and
# never surfaced individually in the UI.
HIDDEN_COUNTRIES: frozenset[str] = frozenset({"CN", "JP", "KR"})


def visible_country_clause():
    """SQLAlchemy WHERE clause: rows whose country is NULL OR not in
    `HIDDEN_COUNTRIES`. NULL-tolerant by design — test fixtures and
    legacy rows without a populated country still flow through.

    Use:
        stmt = stmt.where(visible_country_clause())
    """
    return or_(
        Stock.country.is_(None),
        ~Stock.country.in_(HIDDEN_COUNTRIES),
    )


def is_visible_country(country: str | None) -> bool:
    """Python-side equivalent of `visible_country_clause()` for callsites
    that already have a `country` value in memory (e.g. filtering an
    in-memory metrics list before passing to mover/treemap aggregators)."""
    if country is None:
        return True
    return country.upper() not in HIDDEN_COUNTRIES
