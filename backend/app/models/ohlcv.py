"""Daily OHLCV bar per stock."""
from datetime import date as date_type

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OhlcvDaily(Base):
    __tablename__ = "ohlcv_daily"
    __table_args__ = (
        SAIndex("ix_ohlcv_daily_date", "date"),
    )

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    # Numeric(18, 6), widened from (12, 4) — 8 integer digits was not enough.
    #
    # Split-adjusted history compounds: every reverse split multiplies every
    # earlier bar. SOXS, a 3x inverse ETF with a long reverse-split record,
    # already stored a max close of 47,688,000 and its 2026-07 1:10 reverse
    # split pushed the re-adjusted series past 99,999,999 — so
    # `_rebase_full_history` raised NumericValueOutOfRange, the repair was
    # abandoned, and the stored series kept a 10x discontinuity mid-chart
    # (every EMA/RSI/ATR crossing it was garbage). It retried and failed on
    # every scan.
    #
    # 12 integer digits leaves room for several more reverse splits on the
    # worst instrument in the universe. Postgres numeric is arbitrary-precision
    # internally, so the extra width costs nothing; SQLite ignores precision
    # entirely and was never affected.
    open: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
