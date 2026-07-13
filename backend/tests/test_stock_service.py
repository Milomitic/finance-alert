"""Tests for stock search service."""
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex, StockScore
from app.services.stock_service import StockFilter, get_filter_options, search_stocks


def _seed(db: Session) -> None:
    aapl = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.", sector="Tech", country="US")
    msft = Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft", sector="Tech", country="US")
    eni = Stock(ticker="ENI.MI", exchange="BIT", name="Eni S.p.A.", sector="Energy", country="IT")
    db.add_all([aapl, msft, eni])
    db.flush()
    ndx = Index(code="NDX", name="Nasdaq-100", country="US")
    ftsemib = Index(code="FTSEMIB", name="FTSE MIB", country="IT")
    db.add_all([ndx, ftsemib])
    db.flush()
    db.add(StockIndex(stock_id=aapl.id, index_id=ndx.id))
    db.add(StockIndex(stock_id=msft.id, index_id=ndx.id))
    db.add(StockIndex(stock_id=eni.id, index_id=ftsemib.id))
    db.commit()


def test_search_by_ticker_prefix(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(q="AA"))
    assert [s.stock.ticker for s in page.items] == ["AAPL"]
    assert page.total == 1


def test_search_by_name_substring(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(q="micro"))
    assert [s.stock.ticker for s in page.items] == ["MSFT"]


def test_filter_by_exchange(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(exchanges=["BIT"]))
    assert [s.stock.ticker for s in page.items] == ["ENI.MI"]


def test_filter_by_index_code(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(index_codes=["NDX"]))
    tickers = sorted(s.stock.ticker for s in page.items)
    assert tickers == ["AAPL", "MSFT"]


def test_filter_options_distinct(db: Session) -> None:
    _seed(db)
    opts = get_filter_options(db)
    assert sorted(opts.exchanges) == ["BIT", "NASDAQ"]
    assert sorted(opts.sectors) == ["Energy", "Tech"]
    assert sorted(opts.countries) == ["IT", "US"]
    assert sorted(o.code for o in opts.indices) == ["FTSEMIB", "NDX"]


def _seed_market_caps(db: Session) -> None:
    """Insert 12 stocks with monotonic market caps (1B, 2B, ..., 12B)."""
    for i in range(1, 13):
        db.add(
            Stock(
                ticker=f"T{i:02d}",
                exchange="NASDAQ",
                name=f"Company {i:02d}",
                sector="Tech",
                country="US",
                market_cap=i * 1_000_000_000,
            )
        )
    db.commit()


def test_sort_by_market_cap_desc_global(db: Session) -> None:
    """Sort must be applied BEFORE limit/offset — paging walks the
    globally-sorted result set, not the page-local one. Regression for the
    StocksBrowserPage bug where sort acted only on the current page."""
    _seed_market_caps(db)
    # Page 1: top 5 by market cap desc
    page1 = search_stocks(db, StockFilter(sort_by="market_cap", sort_dir="desc", limit=5, offset=0))
    assert [s.stock.ticker for s in page1.items] == ["T12", "T11", "T10", "T09", "T08"]
    # Page 2: next 5 (still descending across the universe)
    page2 = search_stocks(db, StockFilter(sort_by="market_cap", sort_dir="desc", limit=5, offset=5))
    assert [s.stock.ticker for s in page2.items] == ["T07", "T06", "T05", "T04", "T03"]
    # Page 3: the 2 lowest-cap stocks
    page3 = search_stocks(db, StockFilter(sort_by="market_cap", sort_dir="desc", limit=5, offset=10))
    assert [s.stock.ticker for s in page3.items] == ["T02", "T01"]
    assert page3.has_more is False


def test_sort_by_name_asc(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(sort_by="name", sort_dir="asc"))
    assert [s.stock.ticker for s in page.items] == ["AAPL", "ENI.MI", "MSFT"]


def test_sort_default_is_ticker_asc(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter())
    assert [s.stock.ticker for s in page.items] == ["AAPL", "ENI.MI", "MSFT"]


def test_sort_unknown_column_falls_back_to_ticker(db: Session) -> None:
    """Service-layer guardrail; the API rejects with 422 before reaching here,
    but the service should still produce deterministic output if called
    directly with garbage."""
    _seed(db)
    page = search_stocks(db, StockFilter(sort_by="nope", sort_dir="asc"))
    assert [s.stock.ticker for s in page.items] == ["AAPL", "ENI.MI", "MSFT"]


def _seed_scored(db: Session, ticker: str, **pillars) -> None:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    db.add(StockScore(
        stock_id=s.id,
        composite=pillars.get("composite", 50.0),
        profitability=pillars.get("profitability"),
        sustainability=pillars.get("sustainability"),
        growth=pillars.get("growth"),
        value=pillars.get("value"),
        momentum=pillars.get("momentum"),
        sentiment=pillars.get("sentiment"),
        risk_tier="moderate",
        computed_at=datetime.now(UTC),
        breakdown="{}",
    ))
    db.commit()


def test_search_returns_pillars_and_sorts_by_pillar(db: Session) -> None:
    # (Was sort_by="momentum" — that column was retired from SORTABLE_COLUMNS
    # since the fundamental Momentum pillar is always NULL; repointed to a
    # live pillar to keep sort-by-pillar coverage.)
    _seed_scored(db, "AAA", growth=90.0, value=10.0)
    _seed_scored(db, "BBB", growth=10.0, value=90.0)
    page = search_stocks(db, StockFilter(sort_by="growth", sort_dir="desc"))
    assert [i.stock.ticker for i in page.items[:2]] == ["AAA", "BBB"]
    assert page.items[0].score.growth == 90.0


def test_momentum_not_sortable_and_not_in_score_ref(db: Session) -> None:
    """The always-NULL fundamental momentum pillar is dead API surface:
    removed from SORTABLE_COLUMNS (falls back to ticker) and from the
    screener score payload."""
    from app.services.stock_service import SORTABLE_COLUMNS, StockScoreRef

    assert "momentum" not in SORTABLE_COLUMNS
    assert not hasattr(StockScoreRef(), "momentum")
    _seed_scored(db, "AAA")
    _seed_scored(db, "BBB")
    # Direct service call with the retired key degrades to the ticker sort
    # (the requested direction still applies to the fallback column).
    page = search_stocks(db, StockFilter(sort_by="momentum", sort_dir="asc"))
    assert [i.stock.ticker for i in page.items] == ["AAA", "BBB"]


# ── NULLS LAST on ascending sorts ────────────────────────────────────────────

def test_sort_asc_puts_null_scores_last(db: Session) -> None:
    """SQLite's default NULL ordering is NULLS FIRST on ASC — which used to
    put every unscored stock on page 1 of any ascending sort. nullslast()
    must push them after the valued rows."""
    _seed_scored(db, "SCO1", composite=80.0)
    _seed_scored(db, "SCO2", composite=20.0)
    db.add(Stock(ticker="NOSCORE", exchange="NASDAQ", name="Unscored", country="US"))
    db.commit()

    page = search_stocks(db, StockFilter(sort_by="composite", sort_dir="asc"))
    assert [i.stock.ticker for i in page.items] == ["SCO2", "SCO1", "NOSCORE"]
    # Descending keeps NULLs last too (explicit, direction-independent).
    page = search_stocks(db, StockFilter(sort_by="composite", sort_dir="desc"))
    assert [i.stock.ticker for i in page.items] == ["SCO1", "SCO2", "NOSCORE"]


# ── score_max filter ─────────────────────────────────────────────────────────

def test_filter_by_score_max(db: Session) -> None:
    _seed_scored(db, "HIGH", composite=85.0)
    _seed_scored(db, "MID",  composite=60.0)
    _seed_scored(db, "LOW",  composite=30.0)

    page = search_stocks(db, StockFilter(score_max=65.0))
    tickers = {i.stock.ticker for i in page.items}
    assert tickers == {"MID", "LOW"}
    assert page.total == 2


def test_filter_by_score_max_exact_boundary(db: Session) -> None:
    _seed_scored(db, "EXACT", composite=65.0)
    _seed_scored(db, "ABOVE", composite=66.0)

    page = search_stocks(db, StockFilter(score_max=65.0))
    assert [i.stock.ticker for i in page.items] == ["EXACT"]


def test_filter_by_score_max_and_min_score_range(db: Session) -> None:
    _seed_scored(db, "X1", composite=20.0)
    _seed_scored(db, "X2", composite=50.0)
    _seed_scored(db, "X3", composite=80.0)

    page = search_stocks(db, StockFilter(min_score=40.0, score_max=70.0))
    assert [i.stock.ticker for i in page.items] == ["X2"]


# ── pillar min filters ───────────────────────────────────────────────────────

def test_filter_by_sustainability_min(db: Session) -> None:
    # (Was test_filter_by_momentum_min — momentum left the FUNDAMENTAL
    # composite, so the momentum_min screener filter was retired. Repointed
    # to a live pillar to keep single-pillar-min coverage.)
    _seed_scored(db, "P1", sustainability=90.0)
    _seed_scored(db, "P2", sustainability=50.0)
    _seed_scored(db, "P3", sustainability=20.0)

    page = search_stocks(db, StockFilter(sustainability_min=60.0))
    assert [i.stock.ticker for i in page.items] == ["P1"]


def test_filter_by_profitability_min(db: Session) -> None:
    _seed_scored(db, "Q1", profitability=80.0)
    _seed_scored(db, "Q2", profitability=40.0)

    page = search_stocks(db, StockFilter(profitability_min=70.0))
    assert [i.stock.ticker for i in page.items] == ["Q1"]


def test_filter_by_multiple_pillar_mins(db: Session) -> None:
    """Only stocks meeting ALL pillar minimums should be returned."""
    # (momentum swapped for sustainability — momentum left the FUNDAMENTAL
    # composite; this still exercises the multi-pillar AND semantics.)
    _seed_scored(db, "GOOD", sustainability=80.0, value=75.0, growth=70.0)
    _seed_scored(db, "BAD_M", sustainability=30.0, value=75.0, growth=70.0)
    _seed_scored(db, "BAD_V", sustainability=80.0, value=20.0, growth=70.0)

    page = search_stocks(db, StockFilter(sustainability_min=60.0, value_min=60.0, growth_min=60.0))
    assert [i.stock.ticker for i in page.items] == ["GOOD"]


def test_filter_pillar_no_match_returns_empty(db: Session) -> None:
    _seed_scored(db, "R1", sentiment=30.0)

    page = search_stocks(db, StockFilter(sentiment_min=80.0))
    assert page.items == []
    assert page.total == 0
