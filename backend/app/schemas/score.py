"""Pydantic schemas for /api/stocks/{ticker}/score and /api/scores/top.

Mirrors the response shape spec'd in docs/scoring-algorithm.md. The breakdown
dict is loose-typed (`dict[str, Any]`) because each sub-score has its own
component layout — and the UI doesn't need a static type for it (it just
iterates components and renders bars). The strict shapes on composite +
sub_scores + risk_tier are what frontend code depends on.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


RiskTier = Literal["conservative", "moderate", "aggressive"]
# V3.2 splits Quality into Profitability + Sustainability. The legacy
# `quality` slot is preserved (computed as the average of the two new
# pillars) so old top-picks queries and saved bookmarks keep working.
ScoreCategory = Literal[
    "composite",
    "quality",  # legacy, = avg(profitability, sustainability)
    "profitability",
    "sustainability",
    "growth",
    "value",
    "momentum",
    "sentiment",
]


class SubScoresOut(BaseModel):
    """Per-pillar 0-100 scores. V3.2 has 6 pillars; `quality` is kept as
    a back-compat alias = avg(profitability, sustainability)."""
    quality: float | None  # legacy
    profitability: float | None
    sustainability: float | None
    growth: float | None
    value: float | None
    momentum: float | None
    sentiment: float | None


class StockScoreOut(BaseModel):
    stock_id: int
    ticker: str
    composite: float
    sub_scores: SubScoresOut
    risk_tier: RiskTier
    computed_at: datetime
    breakdown: dict[str, Any]


class TopPickItemOut(BaseModel):
    stock_id: int
    ticker: str
    name: str
    composite: float
    risk_tier: RiskTier
    sector: str | None = None
    market_cap: int | None = None
    change_pct: float | None = None


class TopPicksOut(BaseModel):
    category: ScoreCategory
    risk: RiskTier | None = None
    items: list[TopPickItemOut]
