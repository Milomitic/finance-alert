"""Alert rules (Tier 1 globals + Tier 2 watchlist overrides) and per-(rule, stock) edge state."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Rule(Base):
    __tablename__ = "rules"
    # Note: no DB-level UNIQUE on (watchlist_id, kind) — Fase 3C composite rules
    # share kind="composite" (or kind="composite_*") and the same scope can hold
    # several. Uniqueness for atomic kinds is enforced API-side in `create_rule`.

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
