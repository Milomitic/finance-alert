"""Hardcoded macro calendar — V1 seed for the /calendar surface.

Why hardcoded: a curated 20-event list covering the next 3 months is more
useful than a generic "every economic release ever" feed scraped from
Trading Economics. We pick only the high-conviction items that an equity
investor actually trades around: FOMC, ECB, BoE, BoJ rate decisions,
US CPI/PPI, NFP, GDP advance/final.

V2 follow-up: integrate FRED / TradingEconomics for live macro events.

Date conventions:
- All dates are *announcement* dates (the wall-clock day the print/decision
  hits the wire), not the data's reference period. So "2026-05-08 NFP" is
  the day NFP for April 2026 is released, not the month it covers.
- FOMC decisions are the second day of the 2-day meeting (when the
  statement + dot plot drop).

Ordering: list is roughly chronological for readability; the helper sorts
on the way out so insertion order doesn't matter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Importance = Literal["high", "medium", "low"]
Region = Literal["US", "EU", "UK", "JP"]


@dataclass(frozen=True)
class MacroEvent:
    date: date
    label: str
    importance: Importance
    region: Region


# Static seed: ~20 events covering ~May 2026 through Aug 2026.
# Edit this list (don't compute it dynamically) — that's the whole point of
# V1 hardcoding. When we add a live feed, this file goes away.
_MACRO_EVENTS: tuple[MacroEvent, ...] = (
    # ----- May 2026 -----
    MacroEvent(date(2026, 5, 1),  "US NFP / Non-Farm Payrolls",      "high",   "US"),
    MacroEvent(date(2026, 5, 8),  "BoE rate decision",                "high",   "UK"),
    MacroEvent(date(2026, 5, 13), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 5, 14), "FOMC rate decision",               "high",   "US"),
    MacroEvent(date(2026, 5, 14), "US PPI release",                   "medium", "US"),
    MacroEvent(date(2026, 5, 28), "US GDP (advance, Q1)",             "high",   "US"),
    # ----- June 2026 -----
    MacroEvent(date(2026, 6, 5),  "US NFP / Non-Farm Payrolls",       "high",   "US"),
    MacroEvent(date(2026, 6, 11), "ECB rate decision",                "high",   "EU"),
    MacroEvent(date(2026, 6, 11), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 6, 12), "US PPI release",                   "medium", "US"),
    MacroEvent(date(2026, 6, 17), "BoJ rate decision",                "medium", "JP"),
    MacroEvent(date(2026, 6, 18), "FOMC rate decision",               "high",   "US"),
    MacroEvent(date(2026, 6, 25), "US GDP (final, Q1)",               "medium", "US"),
    # ----- July 2026 -----
    MacroEvent(date(2026, 7, 3),  "US NFP / Non-Farm Payrolls",       "high",   "US"),
    MacroEvent(date(2026, 7, 15), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 7, 16), "US PPI release",                   "medium", "US"),
    MacroEvent(date(2026, 7, 24), "ECB rate decision",                "high",   "EU"),
    MacroEvent(date(2026, 7, 30), "FOMC rate decision",               "high",   "US"),
    MacroEvent(date(2026, 7, 30), "US GDP (advance, Q2)",             "high",   "US"),
    # ----- August 2026 -----
    MacroEvent(date(2026, 8, 7),  "US NFP / Non-Farm Payrolls",       "high",   "US"),
    MacroEvent(date(2026, 8, 12), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 8, 13), "US PPI release",                   "medium", "US"),
)


def get_macro_events(
    date_from: date,
    date_to: date,
    importance_filter: set[Importance] | None = None,
) -> list[MacroEvent]:
    """Return events in [date_from, date_to] (inclusive on both ends).

    `importance_filter`: if provided, only events whose importance is in the
    set are returned. None means no importance filtering (all returned).

    Output is sorted by (date asc, importance desc) — within a single day,
    high-importance events come first. The aggregator may re-sort relative
    to earnings; this is just the macro-only baseline ordering.
    """
    # Importance ordering for stable sort — high first
    importance_rank = {"high": 0, "medium": 1, "low": 2}

    out = [
        e for e in _MACRO_EVENTS
        if date_from <= e.date <= date_to
        and (importance_filter is None or e.importance in importance_filter)
    ]
    out.sort(key=lambda e: (e.date, importance_rank.get(e.importance, 99)))
    return out
