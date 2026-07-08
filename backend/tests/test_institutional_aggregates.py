"""Honest aggregates in `institutional_service.get_aggregate_stats` (lane S1).

Covers the three audit-2026-07-07 guards:

1. unsubstantiated "new" rows (single-filing funds — no baseline to prove a
   position is actually new) never surface in recent_buys;
2. fossil "latest" filings (older than MAX_FILING_AGE_MONTHS) are excluded
   from every aggregate instead of mixing 2014 data into 2026 rollups;
3. dual share classes (GOOG/GOOGL, BRK, ...) are consolidated onto the
   primary ticker in most_picked so a dual-class holder counts once;

plus the persist-path fix: NULL-period scrapes are SKIPPED, not persisted
under a synthetic period_end_date=today().
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Institutional, InstitutionalFiling, InstitutionalHolding
from app.services import institutional_service
from app.services.institutional_scraper import (
    ScrapedFiling,
    ScrapedHolding,
    ScrapedManager,
)

# Periods relative to today so the 18-month freshness cutoff behaves the
# same regardless of when the suite runs.
FRESH = date.today() - timedelta(days=40)
PRIOR = date.today() - timedelta(days=130)
FOSSIL = date(2014, 6, 30)


def _inst(db: Session, slug: str, name: str | None = None) -> Institutional:
    row = Institutional(
        slug=slug, name=name or slug.upper(), type="superinvestor", source="dataroma"
    )
    db.add(row)
    db.flush()
    return row


def _filing(db: Session, inst: Institutional, period_end: date) -> InstitutionalFiling:
    row = InstitutionalFiling(institutional_id=inst.id, period_end_date=period_end)
    db.add(row)
    db.flush()
    return row


def _holding(
    db: Session,
    filing: InstitutionalFiling,
    ticker: str,
    *,
    action: str | None = None,
    value_usd: int = 1_000_000,
    pct: float = 5.0,
) -> InstitutionalHolding:
    row = InstitutionalHolding(
        filing_id=filing.id,
        ticker=ticker,
        company_name=ticker,
        shares=100,
        value_usd=value_usd,
        portfolio_pct=pct,
        action=action,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# 1. Unsubstantiated "new" never reaches recent_buys
# ---------------------------------------------------------------------------

def test_recent_buys_excludes_unsubstantiated_new(db: Session) -> None:
    """A "new" on a fund's ONLY filing has no prior-filing evidence — even
    if bad data re-stamps action='new' upstream (the pre-repair bug), the
    aggregate must never resurface it. A fund WITH history keeps its "new"."""
    # Single-filing fund: "new" is unprovable → must be excluded.
    single = _inst(db, "single-filing-fund")
    f1 = _filing(db, single, FRESH)
    _holding(db, f1, "NVDA", action="new", value_usd=9_000_000_000)

    # Two-filing fund: the FRESH "new" has a PRIOR baseline → substantiated.
    seasoned = _inst(db, "seasoned-fund")
    _filing(db, seasoned, PRIOR)
    f2 = _filing(db, seasoned, FRESH)
    _holding(db, f2, "AMD", action="new", value_usd=1_000_000)

    stats = institutional_service.get_aggregate_stats(db)
    buy_tickers = {b.ticker for b in stats.recent_buys}
    assert "AMD" in buy_tickers
    assert "NVDA" not in buy_tickers


def test_recent_buys_add_rows_unaffected_by_new_guard(db: Session) -> None:
    """The substantiation guard applies to "new" only: an "add" from a
    single-filing fund is still legitimate data (Dataroma precomputes it)."""
    fund = _inst(db, "dataroma-fund")
    f = _filing(db, fund, FRESH)
    _holding(db, f, "MSFT", action="add", value_usd=2_000_000)

    stats = institutional_service.get_aggregate_stats(db)
    assert {b.ticker for b in stats.recent_buys} == {"MSFT"}


# ---------------------------------------------------------------------------
# 2. Fossil filings out of every aggregate
# ---------------------------------------------------------------------------

def test_aggregates_exclude_fossil_latest_filings(db: Session) -> None:
    """A fund whose LATEST filing is from 2014 contributes nothing: not to
    most_picked (holder count/names), not to recent buys, not to sector
    tilt. Same 18-month cutoff as `holders_for_ticker`."""
    dead = _inst(db, "dead-fund", name="Dead Fund LP")
    f_old = _filing(db, dead, FOSSIL)
    _holding(db, f_old, "AAPL", action="add", value_usd=50_000_000_000)

    live = _inst(db, "live-fund", name="Live Fund LP")
    f_new = _filing(db, live, FRESH)
    _holding(db, f_new, "AAPL", action="add", value_usd=1_000_000)

    stats = institutional_service.get_aggregate_stats(db)

    assert len(stats.most_picked) == 1
    row = stats.most_picked[0]
    assert row.ticker == "AAPL"
    assert row.holder_count == 1                      # dead fund not counted
    assert row.holders == ["Live Fund LP"]            # nor named
    assert row.total_value_usd == 1_000_000           # nor its $ summed

    assert all(b.institutional_slug != "dead-fund" for b in stats.recent_buys)


def test_aggregate_empty_when_only_fossils_exist(db: Session) -> None:
    dead = _inst(db, "dead-fund")
    f_old = _filing(db, dead, FOSSIL)
    _holding(db, f_old, "AAPL", action="add")

    stats = institutional_service.get_aggregate_stats(db)
    assert stats.most_picked == []
    assert stats.recent_buys == []
    assert stats.recent_sells == []
    assert stats.sector_tilt == {}


# ---------------------------------------------------------------------------
# 3. Share-class consolidation in most_picked
# ---------------------------------------------------------------------------

def test_most_picked_merges_share_classes(db: Session) -> None:
    """GOOG + GOOGL are the same conviction: three funds (one on each class
    plus one holding BOTH) must produce a single row under the primary
    ticker with holder_count=3 — the dual-class fund counts ONCE
    (COUNT(DISTINCT institutional_id) semantics preserved)."""
    fund_c = _inst(db, "class-c-fund", name="Class C Fund")
    _holding(db, _filing(db, fund_c, FRESH), "GOOG", value_usd=100, pct=10.0)

    fund_a = _inst(db, "class-a-fund", name="Class A Fund")
    _holding(db, _filing(db, fund_a, FRESH), "GOOGL", value_usd=200, pct=8.0)

    fund_both = _inst(db, "dual-class-fund", name="Dual Class Fund")
    f_both = _filing(db, fund_both, FRESH)
    _holding(db, f_both, "GOOG", value_usd=300, pct=6.0)
    _holding(db, f_both, "GOOGL", value_usd=400, pct=4.0)

    stats = institutional_service.get_aggregate_stats(db)
    tickers = [r.ticker for r in stats.most_picked]
    assert tickers == ["GOOG"]                        # one row, primary class
    row = stats.most_picked[0]
    assert row.holder_count == 3                      # dual-class fund counted once
    assert row.total_value_usd == 100 + 200 + 300 + 400
    assert sorted(row.holders) == ["Class A Fund", "Class C Fund", "Dual Class Fund"]


def test_most_picked_merges_berkshire_classes(db: Session) -> None:
    fund_a = _inst(db, "brk-a-holder")
    _holding(db, _filing(db, fund_a, FRESH), "BRK.A", value_usd=500)

    fund_b = _inst(db, "brk-b-holder")
    _holding(db, _filing(db, fund_b, FRESH), "BRK-B", value_usd=700)

    stats = institutional_service.get_aggregate_stats(db)
    assert [r.ticker for r in stats.most_picked] == ["BRK-B"]
    assert stats.most_picked[0].holder_count == 2
    assert stats.most_picked[0].total_value_usd == 1200


# ---------------------------------------------------------------------------
# Persist path: NULL-period scrapes are skipped, not backdated to today
# ---------------------------------------------------------------------------

def test_persist_skips_null_period_scrapes(db: Session) -> None:
    """A scrape whose header didn't parse has no real quarter-end: the old
    behavior minted period_end_date=today(), fabricating a filing that then
    won as "latest" everywhere. It must be skipped entirely."""
    manager = ScrapedManager(code="XX", slug="xx-fund", name="XX Fund")
    broken = ScrapedFiling(
        code="XX",
        period_end_date=None,
        total_value_usd=1_000_000,
        holdings=[
            ScrapedHolding(
                ticker="AAPL", company_name="Apple", shares=10,
                value_usd=1_000_000, portfolio_pct=100.0,
                qoq_change_pct=None, qoq_change_shares=None, action="add",
            )
        ],
    )

    summary = institutional_service.persist_scrape_results(db, [(manager, broken)])

    assert summary.filings_skipped_no_period == 1
    assert summary.filings_added == 0
    assert summary.holdings_inserted == 0
    # Nothing persisted: no synthetic-today filing, no orphan holdings.
    assert db.execute(select(InstitutionalFiling)).scalars().all() == []
    assert db.execute(select(InstitutionalHolding)).scalars().all() == []


def test_persist_still_ingests_valid_filings_alongside_broken_ones(db: Session) -> None:
    manager_ok = ScrapedManager(code="OK", slug="ok-fund", name="OK Fund")
    good = ScrapedFiling(
        code="OK",
        period_end_date=FRESH,
        total_value_usd=2_000_000,
        holdings=[
            ScrapedHolding(
                ticker="MSFT", company_name="Microsoft", shares=5,
                value_usd=2_000_000, portfolio_pct=100.0,
                qoq_change_pct=None, qoq_change_shares=None, action="add",
            )
        ],
    )
    manager_ko = ScrapedManager(code="KO", slug="ko-fund", name="KO Fund")
    broken = ScrapedFiling(code="KO", period_end_date=None, total_value_usd=None)

    summary = institutional_service.persist_scrape_results(
        db, [(manager_ok, good), (manager_ko, broken)]
    )

    assert summary.filings_added == 1
    assert summary.filings_skipped_no_period == 1
    assert summary.holdings_inserted == 1
    periods = db.execute(select(InstitutionalFiling.period_end_date)).scalars().all()
    assert periods == [FRESH]                        # no synthetic today() row


def test_upsert_filing_rejects_null_period(db: Session) -> None:
    """Defense in depth: even a direct caller can't persist a NULL period."""
    inst = _inst(db, "direct-caller")
    broken = ScrapedFiling(code="DC", period_end_date=None, total_value_usd=None)
    with pytest.raises(ValueError, match="period_end_date"):
        institutional_service.upsert_filing(db, inst, broken)
