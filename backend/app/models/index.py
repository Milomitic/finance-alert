"""Index model + many-to-many membership table."""
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Index(Base):
    __tablename__ = "indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)


class StockIndex(Base):
    __tablename__ = "stock_indices"

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    index_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("indices.id", ondelete="CASCADE"), primary_key=True
    )
