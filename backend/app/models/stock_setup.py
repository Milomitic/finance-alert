"""Setups — detector conditions converging, before the trigger fires.

Deliberately a SEPARATE table from `alerts`. A signal means "this condition
matched on bar X"; a setup means "this condition has NOT matched yet". Mixing
them would corrupt `signal_outcomes`, which labels forward returns from the
match date and is the single source of truth for whether the engine works.

The lifecycle is the point. A setup is not just a notification — it is a
falsifiable claim that resolves:

    active ──► converted   the detector fired; `lead_days` records how much
    │                      warning this setup actually gave
    └───────► expired      the conditions decayed without firing

Those two counts give the conversion rate, and `lead_days` gives the realised
lead time. Both are facts about the system, measurable from day one, requiring
no prediction of the market — which is exactly why this feature can ship
before any study exists to justify it.

One row per (stock, detector): a setup that keeps holding is UPDATED, not
duplicated, so `first_seen_at` stays the honest start of the wait.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

STATUS_ACTIVE = "active"
STATUS_CONVERTED = "converted"
STATUS_EXPIRED = "expired"


class StockSetup(Base):
    __tablename__ = "stock_setups"
    __table_args__ = (
        # One live row per (stock, detector). Re-detection updates it.
        UniqueConstraint("stock_id", "detector", name="uq_stock_setups_stock_detector"),
        # The list view is "active, best convenience first".
        SAIndex("ix_stock_setups_status_convenience", "status", "convenience"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    # Which detector this anticipates. Not a FK — detectors are code, not rows.
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    tone: Mapped[str] = mapped_column(String(8), nullable=False)

    # 0..1, how much of the gate chain holds. Never 1.0 — at 1.0 it is a signal.
    proximity: Mapped[float] = mapped_column(Float, nullable=False)
    # 0..100 ATTENTION score used for ordering. NOT a probability and never
    # presented as one — see app/signals/setups/base.py:convenience.
    convenience: Mapped[float] = mapped_column(Float, nullable=False)
    # Plain-language "what still has to happen" — the actionable part.
    missing: Mapped[str] = mapped_column(Text, nullable=False)
    factors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    annotations_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_ACTIVE)
    # Whether this setup is currently in the surfaced shortlist (top N of its
    # detector). NOT a delete, deliberately: dropping the row would destroy
    # `first_seen_at`, and a setup oscillating around the cap boundary would
    # restart its clock every time it re-entered — quietly zeroing the one
    # number this feature is judged by.
    shortlisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set on conversion: the alert the setup turned into, and how many days of
    # warning it gave. `lead_days` is the number this whole feature exists to
    # produce — if it trends to 0, setups are not buying any time.
    converted_alert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
