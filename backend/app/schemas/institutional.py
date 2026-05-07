"""Institutional / superinvestor portfolio schemas (Pydantic v2).

These schemas are flat DTOs — no nested ORM relationships. The
service layer returns dataclasses; the API layer maps them to these
Pydantic models with `.model_validate(obj)` (Pydantic auto-detects
attribute access since `from_attributes=True`).
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


# Discriminated kind labels — kept open as plain strings so a Phase 2
# source can add new types ("hedge_fund", "endowment", "sovereign")
# without breaking the schema.
InstitutionalType = Literal["superinvestor", "institutional", "hedge_fund"]


class InstitutionalSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str
    manager_name: str | None = None
    type: str
    source: str
    source_url: str | None = None
    description: str | None = None
    aum_usd: int | None = None
    latest_period_end: date | None = None
    total_value_usd: int | None = None
    total_positions: int | None = None


class HoldingDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    company_name: str | None = None
    shares: int | None = None
    value_usd: int | None = None
    portfolio_pct: float | None = None
    qoq_change_pct: float | None = None
    qoq_change_shares: int | None = None
    action: str | None = None
    stock_id: int | None = None
    stock_country: str | None = None
    stock_sector: str | None = None


class InstitutionalDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    institutional: InstitutionalSummaryOut
    holdings: list[HoldingDetailOut]
    filed_date: date | None = None
    available_periods: list[date]


class TickerAggregateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    company_name: str | None = None
    holder_count: int
    total_value_usd: int
    total_pct_sum: float
    holders: list[str]
    stock_id: int | None = None
    stock_country: str | None = None
    stock_sector: str | None = None


class ActionAggregateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    company_name: str | None = None
    institutional_slug: str
    institutional_name: str
    period_end_date: date
    action: str
    qoq_change_pct: float | None = None
    portfolio_pct: float | None = None


class AggregateStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    most_picked: list[TickerAggregateOut]
    recent_buys: list[ActionAggregateOut]
    recent_sells: list[ActionAggregateOut]
    sector_tilt: dict[str, int]


class TickerHolderOut(BaseModel):
    """Used by the `InstitutionalHoldersCard` on stock detail pages.

    Each row is one fund holding the ticker as of its latest filing.
    """
    model_config = ConfigDict(from_attributes=True)
    institutional_id: int
    institutional_slug: str
    institutional_name: str
    institutional_manager: str | None = None
    institutional_type: str
    period_end_date: date
    shares: int | None = None
    value_usd: int | None = None
    portfolio_pct: float | None = None
    qoq_change_pct: float | None = None
    action: str | None = None


class TickerHoldersOut(BaseModel):
    ticker: str
    holders: list[TickerHolderOut]
