"""Alert rules (Tier 1 globals + Tier 2 watchlist overrides) and per-(rule, stock) edge state."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (
        # Note: SQLite treats NULL as distinct in UNIQUE — so multiple Tier 1 rules
        # cannot share a kind (good), and multiple Tier 2 overrides cannot collide
        # for the same (watchlist_id, kind).
        UniqueConstraint("watchlist_id", "kind", name="uq_rules_watchlist_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL => Tier 1 (global). Non-null => Tier 2 (override for that watchlist).
    watchlist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # JSON-serialized parameters (e.g. {"period": 14, "threshold": 30}).
    params: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RuleState(Base):
    """Edge-trigger state: was the condition true at the previous evaluation?"""

    __tablename__ = "rule_states"

    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rules.id", ondelete="CASCADE"), primary_key=True
    )
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    last_evaluation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
