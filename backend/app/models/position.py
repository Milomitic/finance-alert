"""Position model — a tracked trade born from a playbook entry.

Closes the signal → trade → outcome loop: the user clicks "Track this trade"
on an alert's playbook, the entry/stop/target are persisted here, live P&L is
computed read-time from the quote layer, and stop/target hits are detected by
the scan (EOD) and the live sweep (intraday). NOT a watchlist (that feature
was deliberately dropped — see migration e0489f561198): a position carries
trade economics and a lifecycle, not a symbol list.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        SAIndex("ix_positions_stock_id", "stock_id"),
        SAIndex("ix_positions_closed_at", "closed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    # The alert whose playbook generated this position (SET NULL if the alert
    # is ever deleted — the position outlives its origin).
    alert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False, default="long")
    entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    # Share count; NULL = notional tracking (P&L in % only).
    size: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    # "stop" | "target" | "manual" — how the position was closed.
    exit_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # USD per 1 unit of the stock's currency, stamped when the position was
    # opened and when it was closed. `realized_usd` used to convert at READ
    # time, so a trade closed months ago reported a different USD result every
    # time the rate moved. The realised leg now uses `exit_fx_rate`; the
    # unrealised leg still marks to the CURRENT rate, because an open position
    # is a mark-to-market and should move with the currency. NULL on rows that
    # predate the book — they keep converting at the current rate, which is
    # what was already happening to them.
    entry_fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    exit_fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
