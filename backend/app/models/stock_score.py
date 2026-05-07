"""Per-stock composite score + 5 sub-scores + risk tier + breakdown JSON.

One row per stock (PK = stock_id). Recomputed at the end of every successful
scan run and after warmup_fundamentals. The breakdown column stores the raw
inputs + per-component points so the UI can show "why this score" without
re-fetching upstream data.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StockScore(Base):
    __tablename__ = "stock_scores"
    __table_args__ = (
        SAIndex("ix_stock_scores_composite", "composite"),
        SAIndex("ix_stock_scores_risk_tier", "risk_tier"),
    )

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    composite: Mapped[float] = mapped_column(Float, nullable=False)
    # quality kept for backward-compat during the V3.2 transition; new
    # consumers should read profitability + sustainability instead.
    quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    profitability: Mapped[float | None] = mapped_column(Float, nullable=True)
    sustainability: Mapped[float | None] = mapped_column(Float, nullable=True)
    growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    breakdown: Mapped[str] = mapped_column(Text, nullable=False)
