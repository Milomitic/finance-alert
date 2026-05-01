"""Daily OHLCV bar per stock."""
from datetime import date as date_type

from sqlalchemy import BigInteger, Date, ForeignKey, Index as SAIndex, Integer, Numeric
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
    open: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
