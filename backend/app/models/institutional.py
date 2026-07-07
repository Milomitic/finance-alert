"""Institutional / superinvestor portfolio tracking.

Three tables:
  - `institutionals` - one row per tracked entity (Buffett / Berkshire,
    Munger / Daily Journal, Burry / Scion, BlackRock, ...). Type tags
    distinguish superinvestor vs large institutional vs hedge fund.
  - `institutional_filings` - one row per (institutional, period_end).
    A filing is a 13F-equivalent snapshot at a quarter-end date.
  - `institutional_holdings` - one row per (filing, ticker). Stores the
    position details (shares, value, % of portfolio, Q/Q delta, action).

NO FK from holdings to `stocks.id`: holdings can reference tickers
outside our catalog (niche ADRs, OTC, etc). Resolved at query time
via `Stock.ticker` lookup; non-matched tickers render as static text
in the UI.
"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Institutional(Base):
    """One tracked portfolio (superinvestor, institutional fund, hedge fund)."""

    __tablename__ = "institutionals"
    __table_args__ = (
        SAIndex("ix_institutionals_type", "type"),
        SAIndex("ix_institutionals_source", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    manager_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # "superinvestor" (Dataroma) | "institutional" (SEC 13F) | "hedge_fund" (HedgeFollow)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    aum_usd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # "dataroma"|"sec_13f"|"hedgefollow"
    source_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    filings: Mapped[list["InstitutionalFiling"]] = relationship(
        back_populates="institutional",
        cascade="all, delete-orphan",
    )


class InstitutionalFiling(Base):
    """One 13F-equivalent snapshot. Multiple per institutional (one per Q)."""

    __tablename__ = "institutional_filings"
    __table_args__ = (
        UniqueConstraint(
            "institutional_id", "period_end_date",
            name="uq_filing_institutional_period",
        ),
        SAIndex("ix_filings_period_end", "period_end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institutional_id: Mapped[int] = mapped_column(
        ForeignKey("institutionals.id", ondelete="CASCADE"), nullable=False
    )
    # Quarter end (e.g. 2026-03-31). The filing represents holdings AS OF this date.
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Date the filing was published (typically 30-45 days after period_end).
    filed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_value_usd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_positions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    institutional: Mapped[Institutional] = relationship(back_populates="filings")
    holdings: Mapped[list["InstitutionalHolding"]] = relationship(
        back_populates="filing",
        cascade="all, delete-orphan",
    )


class InstitutionalHolding(Base):
    """One position inside one filing."""

    __tablename__ = "institutional_holdings"
    __table_args__ = (
        SAIndex("ix_holdings_ticker", "ticker"),
        SAIndex("ix_holdings_filing", "filing_id"),
        # Enforced since migration 390120b342e6 (the docstring always promised
        # it; 108 duplicate groups + dot-ticker collisions were merged there).
        SAIndex(
            "uq_inst_holdings_filing_ticker", "filing_id", "ticker", unique=True
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(
        ForeignKey("institutional_filings.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    value_usd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    portfolio_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    qoq_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    qoq_change_shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # "new" | "add" | "reduce" | "sold_out" | "hold"
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)

    filing: Mapped[InstitutionalFiling] = relationship(back_populates="holdings")


class CusipTickerMap(Base):
    """Persistent CUSIP→ticker resolution for the SEC 13F scraper.

    Written on every successful resolution (catalog name-match or SEC
    company_tickers.json second pass) so resolutions are cumulative across
    runs and survive catalog changes. 35% of the SEC dollar value used to sit
    under raw 'CUSIP:xxx' placeholders."""

    __tablename__ = "cusip_ticker_map"
    __table_args__ = (SAIndex("ix_cusip_ticker_map_ticker", "ticker"),)

    cusip: Mapped[str] = mapped_column(String(16), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'catalog' | 'sec_company_tickers' | 'manual'
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    issuer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
