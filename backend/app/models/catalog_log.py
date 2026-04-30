"""Catalog refresh audit log."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CatalogRefreshLog(Base):
    __tablename__ = "catalog_refresh_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    index_code: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    stocks_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stocks_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stocks_removed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
