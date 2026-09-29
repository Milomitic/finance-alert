"""Smoke tests for the dashboard endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_dashboard_summary_requires_auth(db: Session) -> None:
    """Without get_current_user override, the cookie check kicks in -> 401."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/dashboard/summary")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_dashboard_summary_payload_shape(client: TestClient, db: Session) -> None:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    db.commit()
    db.refresh(stock)
    db.add(
        Alert(
            stock_id=stock.id,
            trigger_price=100.0,
            snapshot="{}",
            signal_name="rsi_oversold",
        )
    )
    db.commit()

    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    # Top-level keys
    for key in ("kpis", "alerts_by_day", "top_stocks_30d", "recent_alerts", "system_status"):
        assert key in body, f"missing key {key}"
    # KPIs
    assert body["kpis"]["alerts_last_24h"] == 1
    assert body["kpis"]["stocks_monitored"] == 1
    # alerts_by_day is a list of 30 points (today and 29 days back)
    assert isinstance(body["alerts_by_day"], list)
    assert len(body["alerts_by_day"]) == 30
    # top_stocks contains AAPL
    assert any(s["ticker"] == "AAPL" for s in body["top_stocks_30d"])
    # recent_alerts contains 1 entry
    assert len(body["recent_alerts"]) == 1
    # system_status keys
    assert "telegram_configured" in body["system_status"]


def test_analyst_actions_enriches_current_price(
    client: TestClient, db: Session, monkeypatch
) -> None:
    """The endpoint joins the latest stored close per ticker so the dashboard
    can show the target's implied upside vs the current price."""
    from datetime import date, timedelta

    from app.models import OhlcvDaily
    from app.services import analyst_actions_feed
    from app.services.analyst_actions_feed import AnalystActionFeedItem

    s = Stock(ticker="ADBE", exchange="NASDAQ", name="Adobe")
    db.add(s)
    db.commit()
    db.refresh(s)
    d0 = date(2026, 6, 1)
    for i, close in enumerate((300.0, 310.0, 320.0)):  # latest = 320
        db.add(OhlcvDaily(stock_id=s.id, date=d0 + timedelta(days=i),
                          open=close, high=close, low=close, close=close, volume=1_000))
    db.commit()

    item = AnalystActionFeedItem(
        ticker="ADBE", name="Adobe", date="2026-06-12", firm="Stifel",
        to_grade="Hold", from_grade="Buy", action="down",
        current_price_target=400.0, prior_price_target=420.0,
        price_target_action="Lowers", from_news=False,
    )
    monkeypatch.setattr(analyst_actions_feed, "recent_actions",
                        lambda **kw: [item])

    resp = client.get("/api/dashboard/analyst-actions")
    assert resp.status_code == 200
    rows = resp.json()
    adbe = next(r for r in rows if r["ticker"] == "ADBE")
    assert adbe["current_price"] == 320.0          # latest stored close
    assert adbe["current_price_target"] == 400.0   # +25% upside (FE computes)


def test_analyst_actions_current_price_none_without_ohlcv(
    client: TestClient, db: Session, monkeypatch
) -> None:
    from app.services import analyst_actions_feed
    from app.services.analyst_actions_feed import AnalystActionFeedItem

    s = Stock(ticker="NEWO", exchange="NASDAQ", name="New Co")
    db.add(s)
    db.commit()
    item = AnalystActionFeedItem(
        ticker="NEWO", name="New Co", date="2026-06-12", firm="X",
        to_grade="Buy", from_grade="Hold", action="up",
        current_price_target=10.0, prior_price_target=None,
        price_target_action="Raises", from_news=False,
    )
    monkeypatch.setattr(analyst_actions_feed, "recent_actions",
                        lambda **kw: [item])
    resp = client.get("/api/dashboard/analyst-actions")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["ticker"] == "NEWO")
    assert row["current_price"] is None


def test_le_azioni_sui_titoli_seguiti_restano_oltre_il_tetto(
    client: TestClient, db: Session,
) -> None:
    """FA-113 sulla scheda analisti: con il tetto a 1 il catalogo mostrerebbe
    solo l'azione piu' recente; quella sulla propria posizione, piu' vecchia,
    resta e porta il segno."""
    import time
    from datetime import date, timedelta
    from decimal import Decimal

    from app.models import Position
    from app.services import stock_fundamentals_service
    from app.services.stock_fundamentals_service import AnalystAction, Fundamentals

    oggi = date.today()
    stocks = {}
    for t in ("POS", "NESSUNO"):
        stocks[t] = Stock(ticker=t, exchange="X", name=t)
        db.add(stocks[t])
    db.flush()
    db.add(Position(stock_id=stocks["POS"].id, entry_price=Decimal("10")))
    db.commit()

    def azione(giorni: int, firm: str) -> AnalystAction:
        return AnalystAction(date=(oggi - timedelta(days=giorni)).isoformat(), firm=firm,
                             to_grade="Buy", from_grade="Hold", action="up")

    stock_fundamentals_service._CACHE.clear()
    try:
        stock_fundamentals_service._CACHE["NESSUNO"] = Fundamentals(
            ticker="NESSUNO", analyst_actions=[azione(1, "A"), azione(2, "B")], fetched_at=time.time())
        stock_fundamentals_service._CACHE["POS"] = Fundamentals(
            ticker="POS", analyst_actions=[azione(10, "C")], fetched_at=time.time())
        rows = client.get("/api/dashboard/analyst-actions?limit=1").json()
    finally:
        stock_fundamentals_service._CACHE.clear()
    assert [(r["ticker"], r["firm"], r["rilevanza"]) for r in rows] == [
        ("NESSUNO", "A", None), ("POS", "C", "posizione"),
    ]
