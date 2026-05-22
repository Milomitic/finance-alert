"""Alert events fired on rule edge-transition (False -> True)."""
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Index as SAIndex,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        SAIndex("ix_alerts_triggered_at", "triggered_at"),
        SAIndex("ix_alerts_rule_id", "rule_id"),
        SAIndex("ix_alerts_stock_id", "stock_id"),
        SAIndex("ix_alerts_read_at", "read_at"),
        SAIndex("ix_alerts_archived_at", "archived_at"),
        SAIndex("ix_alerts_signal_name", "signal_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("rules.id", ondelete="CASCADE"), nullable=True
    )
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # The market-data bar date on which the rule's condition matched. This
    # may differ from `triggered_at`: the scan runs daily/on-demand, so the
    # bar with RSI=85 may have closed yesterday or last Friday while the
    # alert row is created when the scan runs today. Storing both dates
    # lets the UI distinguish "the indicator crossed threshold on Friday,
    # the system noticed Monday" — useful when a scan is missed or when
    # backfilling. Nullable for legacy rows from before this column existed.
    signal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Set on alerts produced by the signal engine (rule_id is then None).
    # The "kind" surfaced to the UI is derived as f"signal:{signal_name}".
    signal_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    # JSON snapshot of indicator values at trigger time, e.g.
    # {"rsi": 28.4, "period": 14, "threshold": 30}
    snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
