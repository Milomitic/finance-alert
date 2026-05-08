"""Pydantic schemas for /api/calendar.

The events list is a discriminated union by `kind`: "earnings" or "macro".
Pydantic v2 picks the right shape from the literal field automatically when
the union is declared `Annotated[..., Field(discriminator="kind")]`.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class EarningsEventOut(BaseModel):
    date: date
    kind: Literal["earnings"] = "earnings"
    ticker: str
    name: str
    eps_estimate: float | None = None
    revenue_estimate: float | None = None
    sector: str | None = None
    market_cap: int | None = None
    # Extras used by the right-pane stock list. Optional so older clients /
    # cached responses without these fields still validate.
    forward_pe: float | None = None
    earnings_growth: float | None = None       # YoY EPS growth, fraction
    composite_score: float | None = None       # 0-100 composite score
    risk_tier: Literal["conservative", "moderate", "aggressive"] | None = None
    earnings_when: Literal["pre", "after"] | None = None
    # Phase 3G: post-release reported EPS + surprise vs estimate. Mirrors
    # the MacroEvent's actual_value / surprise_pct so the calendar UI
    # can render a unified "Ultimo / Atteso / Sorpresa" row across both
    # event types.
    eps_reported: float | None = None
    surprise_pct: float | None = None


class MacroObservationOut(BaseModel):
    """One historical print, used for the small sparkline in the
    calendar's macro detail panel."""
    date: date
    value: float | None


class MacroEventOut(BaseModel):
    date: date
    kind: Literal["macro"] = "macro"
    label: str
    importance: Literal["high", "medium", "low"]
    # Expanded from US/EU/UK/JP to cover every market the user tracks.
    # Mirror of `services/calendar_macros.Region`. Frontend's
    # `lib/calendarMeta.ts` REGION_LABEL/FLAG/REGION_FLAG_ASSET need
    # to grow with this set or unmapped codes render as raw 2-letter
    # codes with the generic 📅 fallback.
    region: Literal[
        "US", "EU", "EZ", "UK", "GB", "JP", "KR", "CN", "HK", "CH",
        "DE", "FR", "IT", "ES", "NL", "BE", "IE",
    ]
    # FRED-driven insight fields. Populated when the event came from
    # `macro_release_dates` joined with `macro_observations`; null
    # when the event is from the hardcoded fallback list. The UI
    # renders the prev/change/sparkline only when these are present.
    prev_value: float | None = None
    prev_date: date | None = None     # date of the most-recent prior reading
    prior_value: float | None = None
    prior_date: date | None = None    # date of the reading before that
    change_pct: float | None = None
    unit: str | None = None
    history: list[MacroObservationOut] = []
    # Release time UTC HH:MM ("12:30" = 12:30 UTC = 8:30 ET for US events
    # / 14:30 CET for EU events). None when the schedule is daily without
    # a specific window. The frontend renders it next to the date so the
    # user knows when to watch the print.
    release_time: str | None = None
    # Phase 3G: consensus / actual / surprise (sourced from Forexfactory's
    # free weekly XML feed via `forexfactory_consensus`). None when the
    # event isn't covered by the consensus mapping or the weekly XML
    # doesn't yet have the forecast/actual.
    expected_value: float | None = None
    actual_value: float | None = None
    surprise_pct: float | None = None


CalendarEvent = Annotated[
    Union[EarningsEventOut, MacroEventOut],
    Field(discriminator="kind"),
]


class CalendarOut(BaseModel):
    date_from: date = Field(serialization_alias="from")
    date_to: date = Field(serialization_alias="to")
    events: list[CalendarEvent]

    model_config = {"populate_by_name": True}
