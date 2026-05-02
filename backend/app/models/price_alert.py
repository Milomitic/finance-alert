"""Price-target alert: per-stock, per-instance alert that fires when the stock
price crosses a target threshold. Distinct from signal-based Rules (RSI etc.)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        SAIndex("ix_price_alerts_stock_id", "stock_id"),
        SAIndex("ix_price_alerts_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    target_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # "above" | "below"
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
