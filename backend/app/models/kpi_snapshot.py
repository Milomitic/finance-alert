"""Append-only KPI time series for engine monitoring / continuous improvement.

One row per capture event:
  - kind="scan"          : per-scan health + signal-population snapshot
  - kind="daily_rollup"  : daily outcome rollup (calibration, confluence, data
                           quality) -- accumulates history the on-demand
                           computations would otherwise discard.

`metrics` is a free-form JSON blob (the schema evolves); the indexed columns
(kind, captured_at) carry the query axes. Never mutated -- analysis reads it.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class KpiSnapshot(Base):
    __tablename__ = "kpi_snapshots"
    __table_args__ = (SAIndex("ix_kpi_kind_captured", "kind", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # scan | daily_rollup
    scope: Mapped[str | None] = mapped_column(String(48), nullable=True)
    metrics: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
