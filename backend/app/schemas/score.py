"""Pydantic schemas for /api/stocks/{ticker}/score and /api/scores/top.

Mirrors the response shape spec'd in docs/scoring-algorithm.md. The breakdown
dict is loose-typed (`dict[str, Any]`) because each sub-score has its own
component layout — and the UI doesn't need a static type for it (it just
iterates components and renders bars). The strict shapes on composite +
sub_scores + risk_tier are what frontend code depends on.
"""
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, field_serializer


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
    # Average composite of all scored stocks in this stock's sector — drives the
    # gauge's "media settore" reference marker. None when sector unknown/empty.
    sector_avg: float | None = None
    # Percentile rank (0-100, higher = better) of this composite within the
    # stock's SECTOR / the whole scored UNIVERSE, + the sector peer count. A 72
    # is meaningless absolutely; "9th pct in Tech vs 80th in Utilities" is the
    # decision-useful framing. None when no peers / unknown sector.
    sector_percentile: int | None = None
    universe_percentile: int | None = None
    peer_n: int | None = None
    # Read-time INFORMATIONAL enrichment (governance + analyst signals) — not
    # part of the composite. {governance:{audit,board,compensation,overall},
    # analyst:{recommendation_mean,n_analysts,price_target,target_upside_pct}}.
    quality_extras: dict | None = None

    @field_serializer("computed_at")
    def _serialize_computed_at(self, value: datetime) -> str:
        """SQLite stores DateTime(timezone=True) as naive ISO strings (no
        TZ suffix). When Pydantic serializes a naive datetime via
        `.isoformat()` the result also lacks a TZ marker, and the frontend
        `new Date(iso)` then reads it as LOCAL time — for a user in UTC+2
        that shifts a fresh "now" timestamp ~2 hours into the past, leading
        to the user-reported "Calcolato 2h fa" right after a recompute.

        Backend convention is "all stored datetimes are UTC", so we attach
        UTC explicitly here. Result: `2026-05-11T14:34:01.836551+00:00`
        which `new Date()` parses correctly across browsers."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()


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


class TechnicalScoreOut(BaseModel):
    """Single-stock continuous technical score (composite + dimensions +
    posture). Mirrors the TechnicalScore model."""
    stock_id: int
    ticker: str
    composite: float
    trend: float | None = None
    momentum: float | None = None
    structure: float | None = None
    volume: float | None = None
    rel_strength: float | None = None
    signals: float | None = None
    posture: str
    computed_at: datetime
