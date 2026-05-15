"""Quando un servizio downstream solleva UpstreamError, il router non deve 500
ma degradare gracefully — restituendo i dati disponibili e ignorando quelli mancanti."""
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import UpstreamUnavailable
from app.main import app
from app.models import OhlcvDaily, Stock, User


def _make_client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _seed(db: Session, ticker: str = "AAPL", n_bars: int = 250) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
              sector="Technology", country="US")
    db.add(s)
    db.commit()
    today = date(2026, 5, 2)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        c = 100.0 + 0.1 * i
        db.add(OhlcvDaily(
            stock_id=s.id, date=d,
            open=c, high=c + 0.5, low=c - 0.5, close=c, volume=1_000_000,
        ))
    db.commit()
    return s


def test_fundamentals_handles_upstream_news_error_gracefully(db: Session):
    """Se stock_news_service.get_news esplode con UpstreamError, il router
    /fundamentals risponde 200 invece di 500: il risultato non include le
    analyst actions da news (fallback a solo structured actions)."""
    client = _make_client(db)
    try:
        _seed(db)
        with patch(
            "app.api.stocks.stock_news_service.get_news",
            side_effect=UpstreamUnavailable(
                "yahoo 503", source="yfinance", op="news"
            ),
        ):
            r = client.get("/api/stocks/AAPL/fundamentals")
        assert r.status_code == 200, r.text
        body = r.json()
        # Response should still contain the expected fields
        assert "analyst_actions" in body
        assert "error" in body
    finally:
        app.dependency_overrides.clear()
