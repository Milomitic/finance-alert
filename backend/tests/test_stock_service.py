"""Tests for stock search service."""
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex
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
