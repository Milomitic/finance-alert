"""Tests for GET /api/stocks/{ticker}/ohlcv — the lightweight daily window
used by the annotated signal chart."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ohlcv_window(client: TestClient, db: Session) -> None:
    s = Stock(ticker="OHL", exchange="NASDAQ", name="Ohl", country="US")
    db.add(s)
    db.flush()
    # Seed 15 daily bars (2026-04-01 .. 2026-04-15).
    for i in range(1, 16):
        db.add(OhlcvDaily(
            stock_id=s.id, date=date(2026, 4, i),
            open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000,
        ))
    db.commit()

    # bars=10 is within the [10, 400] clamp -> last 10 bars, ascending.
    r = client.get("/api/stocks/OHL/ohlcv?bars=10")
    assert r.status_code == 200
    bars = r.json()
    assert len(bars) == 10  # last 10 of the 15 seeded
    assert bars[0]["date"] < bars[-1]["date"]  # ascending
    assert {"date", "open", "high", "low", "close", "volume"} <= bars[0].keys()
    # The last 10 of dates 1..15 are 6..15 ascending.
    assert bars[0]["date"] == "2026-04-06"
    assert bars[-1]["date"] == "2026-04-15"
    assert bars[0]["volume"] == 1000


def test_ohlcv_bars_param_clamped_low(client: TestClient, db: Session) -> None:
    """bars below 10 is clamped up to 10."""
    s = Stock(ticker="CLP", exchange="NASDAQ", name="Clp", country="US")
    db.add(s)
    db.flush()
    for i in range(1, 16):
        db.add(OhlcvDaily(
            stock_id=s.id, date=date(2026, 4, i),
            open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000,
        ))
    db.commit()

    r = client.get("/api/stocks/CLP/ohlcv?bars=3")
    assert r.status_code == 200
    assert len(r.json()) == 10  # 3 clamped up to 10


def test_ohlcv_unknown_ticker_returns_empty(client: TestClient) -> None:
    r = client.get("/api/stocks/NOPE/ohlcv")
    assert r.status_code == 200
    assert r.json() == []


def _semina_lunga(db: Session, ticker: str, n: int) -> None:
    """n barre giornaliere consecutive a partire dal 2010-01-01."""
    from datetime import timedelta
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    for i in range(n):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2010, 1, 1) + timedelta(days=i),
                          open=10, high=11, low=9, close=10 + i, volume=5))
    db.commit()


def test_ohlcv_con_dal_supera_il_tetto_delle_400_barre(client: TestClient, db: Session) -> None:
    """Con `dal` la finestra e' un intervallo di DATE, non le ultime N barre:
    dieci anni di storia sono ~2.500 barre, e il tetto del grafico (400) li
    taglierebbe in silenzio."""
    _semina_lunga(db, "LUN", 1000)
    r = client.get("/api/stocks/LUN/ohlcv?dal=2010-01-01")
    assert r.status_code == 200
    bars = r.json()
    assert len(bars) == 1000
    assert bars[0]["date"] == "2010-01-01"
    assert bars[0]["date"] < bars[-1]["date"]


def test_ohlcv_dal_e_al_sono_inclusivi(client: TestClient, db: Session) -> None:
    _semina_lunga(db, "INT", 30)
    bars = client.get("/api/stocks/INT/ohlcv?dal=2010-01-05&al=2010-01-10").json()
    assert [b["date"] for b in bars] == [f"2010-01-{d:02d}" for d in range(5, 11)]


def test_ohlcv_solo_al_resta_l_ultima_finestra_fino_a_quella_data(client: TestClient, db: Session) -> None:
    """`al` senza `dal`: le ultime `bars` barre FINO a quella data."""
    _semina_lunga(db, "FIN", 30)
    bars = client.get("/api/stocks/FIN/ohlcv?bars=10&al=2010-01-20").json()
    assert len(bars) == 10
    assert (bars[0]["date"], bars[-1]["date"]) == ("2010-01-11", "2010-01-20")
