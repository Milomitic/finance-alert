"""Alert rules + per-(rule, stock) edge state.

Pre-May-2026 the table carried a `watchlist_id` FK so a rule could be
either Tier 1 (global, watchlist_id IS NULL) or Tier 2 (override
scoped to a single watchlist). The watchlist feature was removed —
every rule is now global. The migration `*_drop_watchlist.py` drops
the column and the FK; the model just owns the global subset.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Rule(Base):
    __tablename__ = "rules"
    # Uniqueness of (kind) for atomic kinds is enforced API-side in
    # `create_rule` — composite rules share the kind ("composite") and
    # several can coexist.

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
