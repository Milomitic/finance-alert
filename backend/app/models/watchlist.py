"""Watchlist + items models."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True
    )
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
