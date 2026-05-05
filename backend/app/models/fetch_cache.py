"""Persistent L2 cache for slow upstream fetches (yfinance fundamentals + news).

Why a generic table instead of per-kind ones:
- Two kinds today (fundamentals, news), more later (analyst calendars, earnings
  transcripts, …). One table with a `kind` discriminator keeps the migration
  surface tiny.
- The `payload` is opaque JSON — SQL never reads inside it, so per-kind
  columns wouldn't help query plans anyway.

Why we keep an in-memory L1 in front of this table:
- L1 (per-process dict): microsecond hits inside a request hot path.
- L2 (this table): survives restarts so `recompute_all` doesn't have to
  re-warm the cache from yfinance every time uvicorn comes up.
- Network: only when both L1 + L2 miss or the L2 entry is older than its TTL.
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index as SAIndex,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FetchCache(Base):
    """One row per (ticker, kind). UPSERT on every successful upstream fetch."""

    __tablename__ = "fetch_cache"
    __table_args__ = (
        PrimaryKeyConstraint("ticker", "kind", name="pk_fetch_cache"),
        # Useful for "show me everything cached more than 24h ago" sweeps if we
        # ever add a background refresher.
        SAIndex("ix_fetch_cache_fetched_at", "fetched_at"),
    )

    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    # "fundamentals" | "news" — extend as needed. Kept stringly-typed for
    # forward-compat without a migration when adding new kinds.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # JSON-encoded payload. Shape depends on `kind`:
    #   fundamentals → dataclasses.asdict(Fundamentals) flattened
    #   news         → list of {title, link, publisher, published_at}
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    # When the upstream fetch landed. The service layer compares this against
    # its TTL constant (24h for fundamentals, 1h for news) to decide whether
    # to serve from L2 or refetch.
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
