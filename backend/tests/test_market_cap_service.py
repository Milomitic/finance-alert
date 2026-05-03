"""Tests for market_cap_service."""
import pytest
from sqlalchemy.orm import Session

from app.models import Stock
from app.services import market_cap_service
from app.services.market_cap_service import refresh_market_caps


def _seed(db: Session, ticker: str, name: str = "Test") -> Stock:
    s = Stock(ticker=ticker, name=name, exchange="NASDAQ", currency="USD")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_refresh_updates_market_cap_when_yfinance_returns_value(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = _seed(db, "AAPL")
    monkeypatch.setattr(market_cap_service, "_fetch_market_cap", lambda t: 3_000_000_000_000)
    result = refresh_market_caps(db)
    db.refresh(s)
    assert s.market_cap == 3_000_000_000_000
    assert result.stocks_updated == 1
    assert result.stocks_failed == 0


def test_refresh_skips_when_yfinance_returns_none(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = _seed(db, "BADTKR.XX")
    monkeypatch.setattr(market_cap_service, "_fetch_market_cap", lambda t: None)
    result = refresh_market_caps(db)
    db.refresh(s)
    assert s.market_cap is None
    assert result.stocks_updated == 0
    assert result.stocks_failed == 1
    assert "BADTKR.XX" in result.failed_tickers


def test_refresh_continues_after_per_ticker_exception(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _seed(db, "OK1")
    b = _seed(db, "BOOM")
    c = _seed(db, "OK2")

    def fake(ticker: str) -> int | None:
        if ticker == "BOOM":
            raise RuntimeError("yfinance exploded")
        return 1_000_000

    monkeypatch.setattr(market_cap_service, "_fetch_market_cap", fake)
    result = refresh_market_caps(db)
    db.refresh(a)
    db.refresh(b)
    db.refresh(c)
    assert a.market_cap == 1_000_000
    assert c.market_cap == 1_000_000
    assert b.market_cap is None
    assert result.stocks_updated == 2
    assert result.stocks_failed == 1


def test_fetch_market_cap_handles_gbp_pence(monkeypatch: pytest.MonkeyPatch) -> None:
    """LSE stocks return marketCap in pence with currency 'GBp' — must /100."""
    class FakeFastInfo:
        def get(self, key: str, default=None):
            return {"marketCap": 23_311_271_917_422, "currency": "GBp"}.get(key, default)

    class FakeTicker:
        def __init__(self, _t):
            self.fast_info = FakeFastInfo()

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    cap = market_cap_service._fetch_market_cap("HSBA.L")
    # 23,311,271,917,422 pence / 100 = 233,112,719,174 pounds
    assert cap == 233_112_719_174


def test_fetch_market_cap_passes_through_normal_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    """USD/EUR/etc. — value stays as-is."""
    class FakeFastInfo:
        def get(self, key: str, default=None):
            return {"marketCap": 3_000_000_000_000, "currency": "USD"}.get(key, default)

    class FakeTicker:
        def __init__(self, _t):
            self.fast_info = FakeFastInfo()

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    cap = market_cap_service._fetch_market_cap("AAPL")
    assert cap == 3_000_000_000_000
