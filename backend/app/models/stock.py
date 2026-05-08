"""Stock model."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint, func, text as sa_text
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (
        UniqueConstraint("ticker", "exchange", name="uq_stocks_ticker_exchange"),
        SAIndex("ix_stocks_exchange", "exchange"),
        SAIndex("ix_stocks_sector", "sector"),
        SAIndex("ix_stocks_country", "country"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Idempotency flag for the LSE pence->pounds backfill (alembic migration
    # `..._normalize_lse_ohlcv_to_pounds`). Set to True once a stock's
    # ohlcv_daily rows have been divided by 100 to bring them from pence
    # to pounds. New rows inserted via ohlcv_service._upsert_one_stock are
    # already scaled at write time using yfinance fast_info.currency.
    # See docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md.
    ohlcv_in_pounds: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("0"), default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
