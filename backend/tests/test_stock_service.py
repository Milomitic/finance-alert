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
    assert [s.ticker for s in page.items] == ["AAPL"]
    assert page.total == 1


def test_search_by_name_substring(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(q="micro"))
    assert [s.ticker for s in page.items] == ["MSFT"]


def test_filter_by_exchange(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(exchanges=["BIT"]))
    assert [s.ticker for s in page.items] == ["ENI.MI"]


def test_filter_by_index_code(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(index_codes=["NDX"]))
    tickers = sorted(s.ticker for s in page.items)
    assert tickers == ["AAPL", "MSFT"]


def test_filter_options_distinct(db: Session) -> None:
    _seed(db)
    opts = get_filter_options(db)
    assert sorted(opts.exchanges) == ["BIT", "NASDAQ"]
    assert sorted(opts.sectors) == ["Energy", "Tech"]
    assert sorted(opts.countries) == ["IT", "US"]
    assert sorted(o.code for o in opts.indices) == ["FTSEMIB", "NDX"]
