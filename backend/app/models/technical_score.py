"""Per-stock continuous technical score: composite + sub-dimensions + posture.

One row per stock (PK = stock_id), recomputed every scan. Complementary to the
fundamental StockScore: this one captures the technical STATE of the price
action. The breakdown column stores the raw per-dimension inputs for the UI.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TechnicalScore(Base):
    __tablename__ = "technical_scores"
    __table_args__ = (
        SAIndex("ix_technical_scores_composite", "composite"),
        SAIndex("ix_technical_scores_posture", "posture"),
    )

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    composite: Mapped[float] = mapped_column(Float, nullable=False)
    trend: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum: Mapped[float | None] = mapped_column(Float, nullable=True)
    structure: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    rel_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    signals: Mapped[float | None] = mapped_column(Float, nullable=True)
    posture: Mapped[str] = mapped_column(String(16), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    breakdown: Mapped[str] = mapped_column(Text, nullable=False)
