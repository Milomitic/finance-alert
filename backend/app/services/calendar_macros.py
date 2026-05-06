"""Hardcoded macro calendar — V1 seed for the /calendar surface.

Why hardcoded: a curated event list covering the next 3 months is more
useful than a generic "every economic release ever" feed scraped from
Trading Economics. We pick the high-conviction items that an equity
investor actually trades around — central-bank decisions, top
inflation/employment prints, GDP releases, and a few key sentiment
surveys for each region the user tracks.

V2 follow-up: integrate FRED / TradingEconomics for live macro events.

Coverage (regions match the catalog the user tracks):
- US: FOMC, CPI, PPI, NFP, GDP, ISM, Retail Sales, Beige Book
- EU/EZ: ECB rate decisions + minutes, eurozone CPI flash, PMI flash
- DE: ZEW + IFO surveys (monthly sentiment)
- FR / IT / ES: not granular enough for monthly events; covered by EZ
- UK/GB: BoE, UK CPI, UK GDP
- JP: BoJ, Japan CPI, Tankan (quarterly)
- KR: BoK rate decisions (monthly cadence)
- CN: PBoC LPR fixing, China CPI, China PMI (NBS + Caixin)
- HK: covered indirectly by HKMA/Fed peg + China PBoC
- CH: SNB rate decisions (quarterly)

Date conventions:
- All dates are *announcement* dates (the wall-clock day the print/
  decision hits the wire), not the data's reference period. So
  "2026-05-08 NFP" is the day NFP for April 2026 is released.
- FOMC decisions are the second day of the 2-day meeting (when the
  statement + dot plot drop).

Ordering: list is roughly chronological for readability; the helper
sorts on the way out so insertion order doesn't matter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Importance = Literal["high", "medium", "low"]
# Expanded from {US/EU/UK/JP} to cover every market in the catalog.
# Frontend `lib/calendarMeta.ts::REGION_LABEL` + `REGION_FLAG_ASSET`
# need to grow with this set or unmapped codes render with the raw
# 2-letter code as label and the generic 📅 emoji.
Region = Literal[
    "US", "EU", "EZ", "UK", "GB", "JP", "KR", "CN", "HK", "CH",
    "DE", "FR", "IT", "ES", "NL", "BE", "IE",
]


@dataclass(frozen=True)
class MacroEvent:
    date: date
    label: str
    importance: Importance
    region: Region


# Static seed: ~80 events covering ~May 2026 through Aug 2026.
# Edit this list (don't compute it dynamically) — that's the whole point of
# V1 hardcoding. When we add a live feed, this file goes away.
_MACRO_EVENTS: tuple[MacroEvent, ...] = (
    # ════════════════ May 2026 ════════════════
    # US
    MacroEvent(date(2026, 5, 1),  "ISM Manufacturing PMI",            "medium", "US"),
    MacroEvent(date(2026, 5, 1),  "US NFP / Non-Farm Payrolls",       "high",   "US"),
    MacroEvent(date(2026, 5, 5),  "ISM Services PMI",                 "medium", "US"),
    MacroEvent(date(2026, 5, 13), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 5, 14), "US PPI release",                   "medium", "US"),
    MacroEvent(date(2026, 5, 14), "FOMC rate decision",               "high",   "US"),
    MacroEvent(date(2026, 5, 15), "US Retail Sales",                  "medium", "US"),
    MacroEvent(date(2026, 5, 28), "US GDP (advance, Q1)",             "high",   "US"),
    # EU / Eurozone
    MacroEvent(date(2026, 5, 6),  "Eurozone HICP flash (April)",      "high",   "EZ"),
    MacroEvent(date(2026, 5, 22), "Eurozone PMI flash",               "medium", "EZ"),
    # DE
    MacroEvent(date(2026, 5, 13), "ZEW Economic Sentiment (DE)",      "medium", "DE"),
    MacroEvent(date(2026, 5, 26), "IFO Business Climate (DE)",        "medium", "DE"),
    # UK
    MacroEvent(date(2026, 5, 8),  "BoE rate decision",                "high",   "UK"),
    MacroEvent(date(2026, 5, 21), "UK CPI release",                   "high",   "UK"),
    MacroEvent(date(2026, 5, 12), "UK GDP (Q1, prelim)",              "high",   "UK"),
    # JP
    MacroEvent(date(2026, 5, 22), "Japan CPI release",                "medium", "JP"),
    # KR
    MacroEvent(date(2026, 5, 28), "BoK rate decision",                "high",   "KR"),
    # CN
    MacroEvent(date(2026, 5, 9),  "China CPI release",                "medium", "CN"),
    MacroEvent(date(2026, 5, 20), "PBoC LPR fixing",                  "high",   "CN"),
    MacroEvent(date(2026, 5, 31), "China NBS Manufacturing PMI",      "high",   "CN"),

    # ════════════════ June 2026 ════════════════
    # US
    MacroEvent(date(2026, 6, 1),  "ISM Manufacturing PMI",            "medium", "US"),
    MacroEvent(date(2026, 6, 3),  "ISM Services PMI",                 "medium", "US"),
    MacroEvent(date(2026, 6, 5),  "US NFP / Non-Farm Payrolls",       "high",   "US"),
    MacroEvent(date(2026, 6, 11), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 6, 12), "US PPI release",                   "medium", "US"),
    MacroEvent(date(2026, 6, 17), "US Retail Sales",                  "medium", "US"),
    MacroEvent(date(2026, 6, 18), "FOMC rate decision",               "high",   "US"),
    MacroEvent(date(2026, 6, 25), "US GDP (final, Q1)",               "medium", "US"),
    # EU / Eurozone
    MacroEvent(date(2026, 6, 4),  "Eurozone HICP flash (May)",        "high",   "EZ"),
    MacroEvent(date(2026, 6, 11), "ECB rate decision",                "high",   "EU"),
    MacroEvent(date(2026, 6, 23), "Eurozone PMI flash",               "medium", "EZ"),
    # DE
    MacroEvent(date(2026, 6, 10), "ZEW Economic Sentiment (DE)",      "medium", "DE"),
    MacroEvent(date(2026, 6, 24), "IFO Business Climate (DE)",        "medium", "DE"),
    # UK
    MacroEvent(date(2026, 6, 18), "UK CPI release",                   "high",   "UK"),
    MacroEvent(date(2026, 6, 19), "BoE rate decision",                "high",   "UK"),
    # JP
    MacroEvent(date(2026, 6, 17), "BoJ rate decision",                "high",   "JP"),
    MacroEvent(date(2026, 6, 19), "Japan CPI release",                "medium", "JP"),
    # KR
    MacroEvent(date(2026, 6, 26), "BoK rate decision",                "high",   "KR"),
    # CN
    MacroEvent(date(2026, 6, 9),  "China CPI release",                "medium", "CN"),
    MacroEvent(date(2026, 6, 20), "PBoC LPR fixing",                  "high",   "CN"),
    MacroEvent(date(2026, 6, 30), "China NBS Manufacturing PMI",      "high",   "CN"),
    # CH
    MacroEvent(date(2026, 6, 19), "SNB rate decision",                "medium", "CH"),

    # ════════════════ July 2026 ════════════════
    # US
    MacroEvent(date(2026, 7, 1),  "ISM Manufacturing PMI",            "medium", "US"),
    MacroEvent(date(2026, 7, 3),  "US NFP / Non-Farm Payrolls",       "high",   "US"),
    MacroEvent(date(2026, 7, 7),  "ISM Services PMI",                 "medium", "US"),
    MacroEvent(date(2026, 7, 15), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 7, 16), "US PPI release",                   "medium", "US"),
    MacroEvent(date(2026, 7, 17), "US Retail Sales",                  "medium", "US"),
    MacroEvent(date(2026, 7, 30), "FOMC rate decision",               "high",   "US"),
    MacroEvent(date(2026, 7, 30), "US GDP (advance, Q2)",             "high",   "US"),
    # EU / Eurozone
    MacroEvent(date(2026, 7, 1),  "Eurozone HICP flash (June)",       "high",   "EZ"),
    MacroEvent(date(2026, 7, 23), "Eurozone PMI flash",               "medium", "EZ"),
    MacroEvent(date(2026, 7, 24), "ECB rate decision",                "high",   "EU"),
    # DE
    MacroEvent(date(2026, 7, 15), "ZEW Economic Sentiment (DE)",      "medium", "DE"),
    MacroEvent(date(2026, 7, 24), "IFO Business Climate (DE)",        "medium", "DE"),
    # UK
    MacroEvent(date(2026, 7, 16), "UK CPI release",                   "high",   "UK"),
    # JP
    MacroEvent(date(2026, 7, 1),  "BoJ Tankan survey (Q2)",           "high",   "JP"),
    MacroEvent(date(2026, 7, 18), "Japan CPI release",                "medium", "JP"),
    MacroEvent(date(2026, 7, 31), "BoJ rate decision",                "high",   "JP"),
    # KR
    MacroEvent(date(2026, 7, 10), "BoK rate decision",                "high",   "KR"),
    # CN
    MacroEvent(date(2026, 7, 9),  "China CPI release",                "medium", "CN"),
    MacroEvent(date(2026, 7, 15), "China GDP (Q2)",                   "high",   "CN"),
    MacroEvent(date(2026, 7, 21), "PBoC LPR fixing",                  "high",   "CN"),
    MacroEvent(date(2026, 7, 31), "China NBS Manufacturing PMI",      "high",   "CN"),

    # ════════════════ August 2026 ════════════════
    # US
    MacroEvent(date(2026, 8, 3),  "ISM Manufacturing PMI",            "medium", "US"),
    MacroEvent(date(2026, 8, 5),  "ISM Services PMI",                 "medium", "US"),
    MacroEvent(date(2026, 8, 7),  "US NFP / Non-Farm Payrolls",       "high",   "US"),
    MacroEvent(date(2026, 8, 12), "US CPI release",                   "high",   "US"),
    MacroEvent(date(2026, 8, 13), "US PPI release",                   "medium", "US"),
    MacroEvent(date(2026, 8, 14), "US Retail Sales",                  "medium", "US"),
    MacroEvent(date(2026, 8, 21), "Jackson Hole Symposium kickoff",   "medium", "US"),
    MacroEvent(date(2026, 8, 27), "US GDP (second, Q2)",              "medium", "US"),
    # EU / Eurozone
    MacroEvent(date(2026, 8, 4),  "Eurozone HICP flash (July)",       "high",   "EZ"),
    MacroEvent(date(2026, 8, 21), "Eurozone PMI flash",               "medium", "EZ"),
    # DE
    MacroEvent(date(2026, 8, 11), "ZEW Economic Sentiment (DE)",      "medium", "DE"),
    MacroEvent(date(2026, 8, 25), "IFO Business Climate (DE)",        "medium", "DE"),
    # UK
    MacroEvent(date(2026, 8, 6),  "BoE rate decision",                "high",   "UK"),
    MacroEvent(date(2026, 8, 19), "UK CPI release",                   "high",   "UK"),
    # JP
    MacroEvent(date(2026, 8, 21), "Japan CPI release",                "medium", "JP"),
    # KR
    MacroEvent(date(2026, 8, 28), "BoK rate decision",                "high",   "KR"),
    # CN
    MacroEvent(date(2026, 8, 8),  "China CPI release",                "medium", "CN"),
    MacroEvent(date(2026, 8, 20), "PBoC LPR fixing",                  "high",   "CN"),
    MacroEvent(date(2026, 8, 31), "China NBS Manufacturing PMI",      "high",   "CN"),
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
