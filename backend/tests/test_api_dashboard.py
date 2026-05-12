"""Smoke tests for the dashboard endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Rule, Stock, User


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
    rule = Rule(kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(stock)
    db.refresh(rule)
    db.add(
        Alert(
            rule_id=rule.id,
            stock_id=stock.id,
            trigger_price=100.0,
            snapshot="{}",
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
