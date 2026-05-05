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


class MacroEventOut(BaseModel):
    date: date
    kind: Literal["macro"] = "macro"
    label: str
    importance: Literal["high", "medium", "low"]
    region: Literal["US", "EU", "UK", "JP"]


CalendarEvent = Annotated[
    Union[EarningsEventOut, MacroEventOut],
    Field(discriminator="kind"),
]


class CalendarOut(BaseModel):
    date_from: date = Field(serialization_alias="from")
    date_to: date = Field(serialization_alias="to")
    events: list[CalendarEvent]

    model_config = {"populate_by_name": True}
