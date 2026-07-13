"""Append-only history of the Qualità + Tecnico composite scores.

StockScore / TechnicalScore are single-row-per-stock UPSERTs, so neither lens
has ANY history to validate against forward returns. This table snapshots both
composites once per day so the score-IC backtest (roadmap #9) can measure
whether a high composite precedes outperformance — and so a future pillar-weight
change can be A/B'd instead of taken on faith.

Forward-accruing: Qualità history can only build going forward (no point-in-time
fundamentals to reconstruct it); Tecnico is also reconstructable from
ohlcv_daily for an immediate backtest (see app.scripts.score_ic_report).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Index as SAIndex,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ScoreHistory(Base):
    """One daily snapshot of a stock's composite for one lens (qualita|tecnico)."""

    __tablename__ = "score_history"
    __table_args__ = (
        # One snapshot per (stock, lens, day) — the capture pass is idempotent.
        UniqueConstraint("stock_id", "lens", "captured_on", name="uq_score_history_day"),
        SAIndex("ix_score_history_lens_day", "lens", "captured_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lens: Mapped[str] = mapped_column(String(12), nullable=False)  # qualita | tecnico
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    composite: Mapped[float] = mapped_column(Float, nullable=False)
    # Per-pillar/dimension scores as JSON, for attribution + future weight A/B.
    pillars: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
