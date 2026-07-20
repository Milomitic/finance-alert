"""Per-stock chart drawings (horizontal levels + trend lines), persisted so
they survive a browser wipe and sync across devices — the app is now a
multi-device cloud deployment, where the old localStorage-only store meant a
line drawn on the desktop didn't exist on the phone.

One row per drawing. `kind` discriminates the coordinate columns:
  - "horizontal": `price` set, trend columns null.
  - "trend":      `x1/y1/x2/y2` set (x = unix seconds, y = price), price null.
Explicit nullable columns (not JSON) keep it fully portable across the app's
SQLite (local) and Postgres (cloud) backends.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StockDrawing(Base):
    __tablename__ = "stock_drawings"
    __table_args__ = (SAIndex("ix_stock_drawings_stock_id", "stock_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "horizontal" | "trend"

    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    x1: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # unix seconds
    y1: Mapped[float | None] = mapped_column(Float, nullable=True)
    x2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    y2: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
