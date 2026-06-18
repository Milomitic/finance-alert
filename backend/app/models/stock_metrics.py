"""Per-stock EOD market metrics (price, change%, EMA/RSI, 52w, volume).

One row per stock, fully refreshed at each scan end by
`market_stats_service.recompute_snapshot` from the same `StockMetrics` it already
computes for the breadth aggregates. Persisted so the screener can FILTER and
SORT on technical/price criteria (RSI, EMA position, daily change%, 52-week
position, volume spike) that were previously computed and thrown away.

Freshness: EOD — as of the last scan. A stock without a computable close gets no
row, so the screener's LEFT JOIN keeps it visible with NULL metrics.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StockMetrics(Base):
    __tablename__ = "stock_metrics"
    __table_args__ = (
        SAIndex("ix_stock_metrics_rsi14", "rsi14"),
        SAIndex("ix_stock_metrics_change_pct", "change_pct"),
        SAIndex("ix_stock_metrics_last_close", "last_close"),
    )

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # 1-day %
    ema50: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema200: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi14: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_252: Mapped[float | None] = mapped_column(Float, nullable=True)  # 52w high
    low_252: Mapped[float | None] = mapped_column(Float, nullable=True)  # 52w low
    vol_today: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    vol_avg_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)  # vol_today/avg
