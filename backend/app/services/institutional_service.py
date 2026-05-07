"""Institutional portfolios persistence + aggregate queries.

Two layers in this module:

1. **Upsert layer** (`upsert_*` functions) — translate the dataclass DTOs
   from `institutional_scraper` into rows in the `institutionals`,
   `institutional_filings`, `institutional_holdings` tables. Idempotent
   by design: re-running the scraper for the same period replaces the
   holdings (cascade-delete via the FK) and updates aggregate metadata.

2. **Query layer** (`list_institutionals`, `get_institutional_detail`,
   `get_aggregate_stats`, `holders_for_ticker`) — read-only helpers
   consumed by `app/api/institutionals.py`. All return plain dicts /
   dataclasses, no ORM objects, so the API layer can serialize them
   directly without N+1 lazy-loads.

Design notes
------------
- Holdings store `ticker` as a plain string with no FK to `stocks.id`.
  This is intentional: Dataroma exposes positions in tickers we may not
  carry in our catalog (small caps, ADRs, OTC). The query layer
  LEFT-JOINs to `Stock` by ticker only when a row exists.

- "Latest filing" semantics: for each institutional we always read the
  most recent `period_end_date`. Older filings are kept for history but
  are not surfaced in aggregate stats.

- "Most-picked" aggregation: counts how many superinvestors hold a
  given ticker in their LATEST filing. Sums portfolio_pct as a
  secondary "conviction" metric. Sorted by holder_count DESC.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Institutional,
    InstitutionalFiling,
    InstitutionalHolding,
    Stock,
)
from app.services.institutional_scraper import (
    ScrapedFiling,
    ScrapedManager,
)


# ---------------------------------------------------------------------------
# Upsert layer (used by the cron job + the seed script)
# ---------------------------------------------------------------------------

@dataclass
class UpsertResult:
    institutionals_added: int
    institutionals_updated: int
    filings_added: int
    filings_replaced: int
    holdings_inserted: int


def upsert_institutional(
    db: Session,
    manager: ScrapedManager,
    *,
    type_: str = "superinvestor",
    source: str = "dataroma",
) -> tuple[Institutional, bool]:
    """Idempotent upsert by `slug`. Returns (row, created)."""
    row = db.execute(
        select(Institutional).where(Institutional.slug == manager.slug)
    ).scalar_one_or_none()
    if row is None:
        row = Institutional(
            slug=manager.slug,
            name=manager.name,
            manager_name=manager.manager_name,
            type=type_,
            source=source,
            source_url=manager.source_url,
            description=manager.description,
        )
        db.add(row)
        db.flush()
        return row, True
    # Update mutable metadata. AUM stays untouched here: Dataroma's
    # index doesn't expose it; we leave it null until a Phase 2 source
    # supplies the figure.
    row.name = manager.name
    if manager.manager_name:
        row.manager_name = manager.manager_name
    if manager.source_url:
        row.source_url = manager.source_url
    if manager.description:
        row.description = manager.description
    return row, False


def upsert_filing(
    db: Session,
    institutional: Institutional,
    filing: ScrapedFiling,
) -> tuple[InstitutionalFiling, bool]:
    """Upsert one filing snapshot.

    Uniqueness key: (institutional_id, period_end_date). If a filing
    for the same period already exists, we DELETE its holdings and
    re-insert from the scraped data — this is how a "Q1 -> Q1 with
    correction" re-publish (rare but possible) is handled idempotently.

    Returns (filing, created). If period_end_date is None we degrade
    to a synthetic "today" so the upsert can still proceed; the UI
    will show this filing labeled with the scrape date instead of the
    real quarter end.
    """
    period_end = filing.period_end_date or date.today()
    existing = db.execute(
        select(InstitutionalFiling).where(
            InstitutionalFiling.institutional_id == institutional.id,
            InstitutionalFiling.period_end_date == period_end,
        )
    ).scalar_one_or_none()
    if existing is None:
        row = InstitutionalFiling(
            institutional_id=institutional.id,
            period_end_date=period_end,
            total_value_usd=filing.total_value_usd,
            total_positions=len(filing.holdings) or None,
        )
        db.add(row)
        db.flush()
        return row, True
    # Wipe + re-insert holdings: simpler than a per-row diff, and
    # the table is small (one filing ≈ a few dozen to a few hundred rows).
    db.execute(
        delete(InstitutionalHolding).where(
            InstitutionalHolding.filing_id == existing.id
        )
    )
    existing.total_value_usd = filing.total_value_usd
    existing.total_positions = len(filing.holdings) or None
    db.flush()
    return existing, False


def insert_holdings(
    db: Session,
    filing: InstitutionalFiling,
    rows: Sequence,
) -> int:
    """Bulk-insert holdings rows. Caller must have wiped any prior
    rows for this filing (see `upsert_filing`)."""
    if not rows:
        return 0
    objs = [
        InstitutionalHolding(
            filing_id=filing.id,
            ticker=h.ticker,
            company_name=h.company_name,
            shares=h.shares,
            value_usd=h.value_usd,
            portfolio_pct=h.portfolio_pct,
            qoq_change_pct=h.qoq_change_pct,
            qoq_change_shares=h.qoq_change_shares,
            action=h.action,
        )
        for h in rows
    ]
    db.add_all(objs)
    db.flush()
    return len(objs)


def persist_scrape_results(
    db: Session,
    results: Iterable[tuple[ScrapedManager, ScrapedFiling | None]],
) -> UpsertResult:
    """End-to-end persistence of a full scrape pass.

    Commits at the end. On any partial failure we still commit what
    succeeded so the UI shows the partial set rather than nothing.
    Per-manager exceptions are caught and swallowed (logged via the
    scraper layer).
    """
    summary = UpsertResult(0, 0, 0, 0, 0)
    for manager, filing in results:
        if filing is None:
            continue
        inst, created = upsert_institutional(db, manager)
        if created:
            summary.institutionals_added += 1
        else:
            summary.institutionals_updated += 1
        f_row, f_created = upsert_filing(db, inst, filing)
        if f_created:
            summary.filings_added += 1
        else:
            summary.filings_replaced += 1
        summary.holdings_inserted += insert_holdings(db, f_row, filing.holdings)
    db.commit()
    return summary


# ---------------------------------------------------------------------------
# Query layer (used by the API)
# ---------------------------------------------------------------------------

@dataclass
class InstitutionalSummary:
    id: int
    slug: str
    name: str
    manager_name: str | None
    type: str
    source: str
    source_url: str | None
    description: str | None
    aum_usd: int | None
    latest_period_end: date | None
    total_value_usd: int | None
    total_positions: int | None


def list_institutionals(
    db: Session,
    *,
    type_: str | None = None,
    source: str | None = None,
    limit: int = 200,
) -> list[InstitutionalSummary]:
    """All institutionals + their latest filing summary in a single query.

    Uses a correlated subquery to grab MAX(period_end_date) per
    institutional, then joins back to `institutional_filings` to pull
    the metric columns. Ordered by name for stable UI rendering.
    """
    latest_subq = (
        select(
            InstitutionalFiling.institutional_id,
            func.max(InstitutionalFiling.period_end_date).label("max_period"),
        )
        .group_by(InstitutionalFiling.institutional_id)
        .subquery()
    )
    stmt = (
        select(
            Institutional,
            InstitutionalFiling.period_end_date,
            InstitutionalFiling.total_value_usd,
            InstitutionalFiling.total_positions,
        )
        .outerjoin(latest_subq, latest_subq.c.institutional_id == Institutional.id)
        .outerjoin(
            InstitutionalFiling,
            (InstitutionalFiling.institutional_id == Institutional.id)
            & (InstitutionalFiling.period_end_date == latest_subq.c.max_period),
        )
        .order_by(Institutional.name.asc())
        .limit(limit)
    )
    if type_:
        stmt = stmt.where(Institutional.type == type_)
    if source:
        stmt = stmt.where(Institutional.source == source)

    out: list[InstitutionalSummary] = []
    for inst, period_end, total_val, total_pos in db.execute(stmt).all():
        out.append(
            InstitutionalSummary(
                id=inst.id,
                slug=inst.slug,
                name=inst.name,
                manager_name=inst.manager_name,
                type=inst.type,
                source=inst.source,
                source_url=inst.source_url,
                description=inst.description,
                aum_usd=inst.aum_usd,
                latest_period_end=period_end,
                total_value_usd=total_val,
                total_positions=total_pos,
            )
        )
    return out


@dataclass
class HoldingDetail:
    ticker: str
    company_name: str | None
    shares: int | None
    value_usd: int | None
    portfolio_pct: float | None
    qoq_change_pct: float | None
    qoq_change_shares: int | None
    action: str | None
    # Catalog enrichment (None if ticker not in our catalog)
    stock_id: int | None
    stock_country: str | None
    stock_sector: str | None


@dataclass
class InstitutionalDetail:
    institutional: InstitutionalSummary
    holdings: list[HoldingDetail]
    filed_date: date | None
    available_periods: list[date]


def get_institutional_detail(
    db: Session,
    slug: str,
    *,
    period_end: date | None = None,
) -> InstitutionalDetail | None:
    """Return one institutional + the requested filing's holdings.

    `period_end=None` means "latest available". Holdings sorted by
    `portfolio_pct DESC` so the heaviest convictions appear at top.
    Tickers that match a row in `stocks` are enriched with
    `stock_id` + `country` + `sector` for cross-linking in the UI.
    """
    inst = db.execute(
        select(Institutional).where(Institutional.slug == slug)
    ).scalar_one_or_none()
    if inst is None:
        return None

    # Resolve target filing
    filings_q = (
        select(InstitutionalFiling)
        .where(InstitutionalFiling.institutional_id == inst.id)
        .order_by(InstitutionalFiling.period_end_date.desc())
    )
    filings = list(db.execute(filings_q).scalars().all())
    if not filings:
        # Institutional with no filings yet (just registered, not yet scraped)
        summary = InstitutionalSummary(
            id=inst.id, slug=inst.slug, name=inst.name,
            manager_name=inst.manager_name, type=inst.type, source=inst.source,
            source_url=inst.source_url, description=inst.description,
            aum_usd=inst.aum_usd, latest_period_end=None,
            total_value_usd=None, total_positions=None,
        )
        return InstitutionalDetail(
            institutional=summary, holdings=[],
            filed_date=None, available_periods=[],
        )

    if period_end is None:
        target = filings[0]
    else:
        target = next(
            (f for f in filings if f.period_end_date == period_end),
            filings[0],
        )

    # Enrich holdings with catalog data via LEFT JOIN. We dedupe by
    # ticker (catalog has duplicate rows — see CLAUDE.md), picking the
    # first match by id.
    rows = db.execute(
        select(
            InstitutionalHolding,
            Stock.id, Stock.country, Stock.sector,
        )
        .outerjoin(Stock, Stock.ticker == InstitutionalHolding.ticker)
        .where(InstitutionalHolding.filing_id == target.id)
        .order_by(
            InstitutionalHolding.portfolio_pct.desc().nullslast(),
            InstitutionalHolding.value_usd.desc().nullslast(),
        )
    ).all()

    seen_tickers: set[str] = set()
    holdings: list[HoldingDetail] = []
    for h, stock_id, country, sector in rows:
        if h.ticker in seen_tickers:
            continue
        seen_tickers.add(h.ticker)
        holdings.append(
            HoldingDetail(
                ticker=h.ticker,
                company_name=h.company_name,
                shares=h.shares,
                value_usd=h.value_usd,
                portfolio_pct=h.portfolio_pct,
                qoq_change_pct=h.qoq_change_pct,
                qoq_change_shares=h.qoq_change_shares,
                action=h.action,
                stock_id=stock_id,
                stock_country=country,
                stock_sector=sector,
            )
        )

    summary = InstitutionalSummary(
        id=inst.id, slug=inst.slug, name=inst.name,
        manager_name=inst.manager_name, type=inst.type, source=inst.source,
        source_url=inst.source_url, description=inst.description,
        aum_usd=inst.aum_usd, latest_period_end=target.period_end_date,
        total_value_usd=target.total_value_usd,
        total_positions=target.total_positions,
    )
    return InstitutionalDetail(
        institutional=summary,
        holdings=holdings,
        filed_date=target.filed_date,
        available_periods=[f.period_end_date for f in filings],
    )


# ---------------------------------------------------------------------------
# Aggregate stats: most-picked, recent buys/sells, sector tilt
# ---------------------------------------------------------------------------

@dataclass
class TickerAggregate:
    ticker: str
    company_name: str | None
    holder_count: int       # how many institutionals hold it (latest filing each)
    total_value_usd: int    # sum of value_usd across those holders
    total_pct_sum: float    # sum of portfolio_pct (rough conviction proxy)
    holders: list[str]      # institutional names holding it (display)
    stock_id: int | None
    stock_country: str | None
    stock_sector: str | None


@dataclass
class ActionAggregate:
    """One row in the "recent buys" / "recent sells" leaderboard."""
    ticker: str
    company_name: str | None
    institutional_slug: str
    institutional_name: str
    period_end_date: date
    action: str
    qoq_change_pct: float | None
    portfolio_pct: float | None


@dataclass
class AggregateStats:
    most_picked: list[TickerAggregate]
    recent_buys: list[ActionAggregate]
    recent_sells: list[ActionAggregate]
    sector_tilt: dict[str, int]    # sector -> total $ across all latest filings


def _latest_filings_subq(db: Session):
    """Helper: subquery yielding (institutional_id, latest_filing_id)."""
    rank = (
        select(
            InstitutionalFiling.id.label("filing_id"),
            InstitutionalFiling.institutional_id,
            InstitutionalFiling.period_end_date,
        )
        .subquery()
    )
    latest = (
        select(
            InstitutionalFiling.institutional_id,
            func.max(InstitutionalFiling.period_end_date).label("max_period"),
        )
        .group_by(InstitutionalFiling.institutional_id)
        .subquery()
    )
    return rank, latest


def get_aggregate_stats(
    db: Session,
    *,
    type_: str | None = None,
    most_picked_limit: int = 25,
    recent_actions_limit: int = 20,
) -> AggregateStats:
    """Cross-portfolio rollups for the InstitutionalsPage overview.

    All metrics are computed on the LATEST filing per institutional —
    we never mix data across quarters in the same aggregate (would
    double-count a Q4 + Q1 pair for the same fund).
    """
    rank, latest = _latest_filings_subq(db)

    # Latest filing IDs per institutional, optionally filtered by type
    latest_ids_q = (
        select(InstitutionalFiling.id, Institutional.id, Institutional.name)
        .join(Institutional, Institutional.id == InstitutionalFiling.institutional_id)
        .join(
            latest,
            (latest.c.institutional_id == InstitutionalFiling.institutional_id)
            & (latest.c.max_period == InstitutionalFiling.period_end_date),
        )
    )
    if type_:
        latest_ids_q = latest_ids_q.where(Institutional.type == type_)
    latest_rows = db.execute(latest_ids_q).all()
    latest_filing_ids = [r[0] for r in latest_rows]
    inst_name_by_id: dict[int, str] = {r[1]: r[2] for r in latest_rows}

    if not latest_filing_ids:
        return AggregateStats(
            most_picked=[], recent_buys=[], recent_sells=[], sector_tilt={}
        )

    # ---- Most-picked: GROUP BY ticker over the latest filings ----
    mp_rows = db.execute(
        select(
            InstitutionalHolding.ticker,
            func.max(InstitutionalHolding.company_name).label("company_name"),
            func.count(func.distinct(InstitutionalFiling.institutional_id)).label("holder_count"),
            func.coalesce(func.sum(InstitutionalHolding.value_usd), 0).label("total_value"),
            func.coalesce(func.sum(InstitutionalHolding.portfolio_pct), 0.0).label("total_pct"),
        )
        .join(InstitutionalFiling, InstitutionalFiling.id == InstitutionalHolding.filing_id)
        .where(InstitutionalHolding.filing_id.in_(latest_filing_ids))
        .group_by(InstitutionalHolding.ticker)
        .order_by(
            func.count(func.distinct(InstitutionalFiling.institutional_id)).desc(),
            func.coalesce(func.sum(InstitutionalHolding.value_usd), 0).desc(),
        )
        .limit(most_picked_limit)
    ).all()

    # Per-ticker holder names (top 5 each, for display).
    top_tickers = [r[0] for r in mp_rows]
    holder_names_by_ticker: dict[str, list[str]] = defaultdict(list)
    if top_tickers:
        name_rows = db.execute(
            select(
                InstitutionalHolding.ticker,
                Institutional.name,
                InstitutionalHolding.portfolio_pct,
            )
            .join(InstitutionalFiling, InstitutionalFiling.id == InstitutionalHolding.filing_id)
            .join(Institutional, Institutional.id == InstitutionalFiling.institutional_id)
            .where(
                InstitutionalHolding.filing_id.in_(latest_filing_ids),
                InstitutionalHolding.ticker.in_(top_tickers),
            )
            .order_by(InstitutionalHolding.portfolio_pct.desc().nullslast())
        ).all()
        for ticker, name, _pct in name_rows:
            if len(holder_names_by_ticker[ticker]) < 5:
                holder_names_by_ticker[ticker].append(name)

    # Catalog enrichment for top tickers
    catalog_by_ticker: dict[str, tuple[int | None, str | None, str | None]] = {}
    if top_tickers:
        cat_rows = db.execute(
            select(Stock.id, Stock.ticker, Stock.country, Stock.sector)
            .where(Stock.ticker.in_(top_tickers))
        ).all()
        for sid, ticker, country, sector in cat_rows:
            if ticker not in catalog_by_ticker:
                catalog_by_ticker[ticker] = (sid, country, sector)

    most_picked = [
        TickerAggregate(
            ticker=ticker,
            company_name=company_name,
            holder_count=int(holder_count),
            total_value_usd=int(total_value or 0),
            total_pct_sum=float(total_pct or 0.0),
            holders=holder_names_by_ticker.get(ticker, []),
            stock_id=catalog_by_ticker.get(ticker, (None, None, None))[0],
            stock_country=catalog_by_ticker.get(ticker, (None, None, None))[1],
            stock_sector=catalog_by_ticker.get(ticker, (None, None, None))[2],
        )
        for ticker, company_name, holder_count, total_value, total_pct in mp_rows
    ]

    # ---- Recent buys / sells: per-row action filter on latest filings ----
    def _actions(action_set: set[str], limit: int) -> list[ActionAggregate]:
        rows = db.execute(
            select(
                InstitutionalHolding.ticker,
                InstitutionalHolding.company_name,
                Institutional.slug,
                Institutional.name,
                InstitutionalFiling.period_end_date,
                InstitutionalHolding.action,
                InstitutionalHolding.qoq_change_pct,
                InstitutionalHolding.portfolio_pct,
            )
            .join(InstitutionalFiling, InstitutionalFiling.id == InstitutionalHolding.filing_id)
            .join(Institutional, Institutional.id == InstitutionalFiling.institutional_id)
            .where(
                InstitutionalHolding.filing_id.in_(latest_filing_ids),
                InstitutionalHolding.action.in_(list(action_set)),
            )
            .order_by(
                InstitutionalFiling.period_end_date.desc(),
                func.coalesce(
                    func.abs(InstitutionalHolding.qoq_change_pct), 0.0
                ).desc(),
                InstitutionalHolding.portfolio_pct.desc().nullslast(),
            )
            .limit(limit)
        ).all()
        return [
            ActionAggregate(
                ticker=ticker, company_name=company_name,
                institutional_slug=slug, institutional_name=name,
                period_end_date=period_end, action=action,
                qoq_change_pct=qoq, portfolio_pct=pct,
            )
            for ticker, company_name, slug, name, period_end, action, qoq, pct in rows
        ]

    recent_buys = _actions({"new", "add"}, recent_actions_limit)
    recent_sells = _actions({"reduce", "sold_out"}, recent_actions_limit)

    # ---- Sector tilt: sum of value_usd by sector across latest filings ----
    sector_rows = db.execute(
        select(
            Stock.sector,
            func.coalesce(func.sum(InstitutionalHolding.value_usd), 0).label("total"),
        )
        .join(InstitutionalHolding, InstitutionalHolding.ticker == Stock.ticker)
        .where(InstitutionalHolding.filing_id.in_(latest_filing_ids))
        .group_by(Stock.sector)
        .order_by(func.coalesce(func.sum(InstitutionalHolding.value_usd), 0).desc())
    ).all()
    sector_tilt: dict[str, int] = {}
    for sector, total in sector_rows:
        key = sector or "Unknown"
        sector_tilt[key] = sector_tilt.get(key, 0) + int(total or 0)

    return AggregateStats(
        most_picked=most_picked,
        recent_buys=recent_buys,
        recent_sells=recent_sells,
        sector_tilt=sector_tilt,
    )


# ---------------------------------------------------------------------------
# Per-stock card: which superinvestors hold this ticker?
# ---------------------------------------------------------------------------

@dataclass
class TickerHolder:
    institutional_id: int
    institutional_slug: str
    institutional_name: str
    institutional_manager: str | None
    institutional_type: str
    period_end_date: date
    shares: int | None
    value_usd: int | None
    portfolio_pct: float | None
    qoq_change_pct: float | None
    action: str | None


def holders_for_ticker(
    db: Session,
    ticker: str,
    *,
    limit: int = 25,
) -> list[TickerHolder]:
    """Return the list of institutionals holding `ticker` in their
    latest filing. Used by the InstitutionalHoldersCard above the
    InsidersCard on stock detail pages.

    Sorted by `portfolio_pct DESC` (conviction first), with `value_usd`
    as tiebreaker. Limit is 25 by default — beyond that the card would
    bleed into a full-page table; UI shows a "view all" link.
    """
    rank, latest = _latest_filings_subq(db)
    rows = db.execute(
        select(
            Institutional.id,
            Institutional.slug,
            Institutional.name,
            Institutional.manager_name,
            Institutional.type,
            InstitutionalFiling.period_end_date,
            InstitutionalHolding.shares,
            InstitutionalHolding.value_usd,
            InstitutionalHolding.portfolio_pct,
            InstitutionalHolding.qoq_change_pct,
            InstitutionalHolding.action,
        )
        .join(
            InstitutionalFiling,
            InstitutionalFiling.id == InstitutionalHolding.filing_id,
        )
        .join(
            Institutional,
            Institutional.id == InstitutionalFiling.institutional_id,
        )
        .join(
            latest,
            (latest.c.institutional_id == Institutional.id)
            & (latest.c.max_period == InstitutionalFiling.period_end_date),
        )
        .where(InstitutionalHolding.ticker == ticker)
        .order_by(
            InstitutionalHolding.portfolio_pct.desc().nullslast(),
            InstitutionalHolding.value_usd.desc().nullslast(),
        )
        .limit(limit)
    ).all()

    out: list[TickerHolder] = []
    for (
        inst_id, slug, name, manager_name, type_, period_end,
        shares, value_usd, portfolio_pct, qoq_change_pct, action,
    ) in rows:
        out.append(
            TickerHolder(
                institutional_id=inst_id,
                institutional_slug=slug,
                institutional_name=name,
                institutional_manager=manager_name,
                institutional_type=type_,
                period_end_date=period_end,
                shares=shares,
                value_usd=value_usd,
                portfolio_pct=portfolio_pct,
                qoq_change_pct=qoq_change_pct,
                action=action,
            )
        )
    return out
