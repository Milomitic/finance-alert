"""Smoke tests for the /api/positions CRUD endpoints (tracked trades, B3-6)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, User
from app.services import position_service


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    s = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add_all([user, s]); db.commit()
    # Two stored bars so the "default entry/exit price" path has an EOD
    # fallback (the live-quote layer yields an errored quote under the
    # test network guard, so the stored close is what gets picked).
    today = date(2026, 6, 2)
    for d, c in ((today - timedelta(days=1), 148.0), (today, 150.0)):
        db.add(OhlcvDaily(stock_id=s.id, date=d, open=c, high=c, low=c, close=c, volume=1))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_requires_auth(db):
    """No get_current_user override → the cookie-session dependency rejects."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        r = c.get("/api/positions")
        assert r.status_code == 401
        r = c.post("/api/positions", json={"ticker": "AAPL", "entry_price": 100.0})
        assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_open_list_edit_close_delete_flow(client):
    r = client.post("/api/positions", json={
        "ticker": "AAPL", "side": "long", "entry_price": 150.0,
        "stop_price": 140.0, "target_price": 170.0, "size": 10.0,
        "notes": "dal playbook",
    })
    assert r.status_code == 201, r.text
    pos = r.json()
    pid = pos["id"]
    assert pos["ticker"] == "AAPL"
    assert pos["side"] == "long"
    assert pos["entry_price"] == 150.0
    assert pos["closed_at"] is None
    # Read-time enrichment: live quote errors under the network guard →
    # EOD fallback from the stored close (150.0) → flat P&L.
    assert pos["last_price"] == 150.0
    assert pos["price_source"] == "eod"
    assert pos["unrealized_pct"] == pytest.approx(0.0)

    r = client.get("/api/positions?status=open")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Edit stop/target.
    r = client.patch(f"/api/positions/{pid}", json={"stop_price": 145.0})
    assert r.status_code == 200
    assert r.json()["stop_price"] == 145.0

    # Manual close with an explicit exit price.
    r = client.patch(f"/api/positions/{pid}", json={"close": True, "exit_price": 165.0})
    assert r.status_code == 200
    body = r.json()
    assert body["exit_reason"] == "manual"
    assert body["exit_price"] == 165.0
    assert body["realized_pct"] == pytest.approx(10.0)
    assert body["realized_abs"] == pytest.approx(150.0)

    # Closing again is a state conflict; editing a closed position too.
    r = client.patch(f"/api/positions/{pid}", json={"close": True, "exit_price": 100.0})
    assert r.status_code == 409
    r = client.patch(f"/api/positions/{pid}", json={"stop_price": 1.0})
    assert r.status_code == 409

    assert len(client.get("/api/positions?status=closed").json()) == 1
    assert client.get("/api/positions?status=open").json() == []
    assert len(client.get("/api/positions").json()) == 1  # default: all

    r = client.delete(f"/api/positions/{pid}")
    assert r.status_code == 204
    assert client.get("/api/positions").json() == []


def test_open_defaults_entry_to_last_close(client):
    r = client.post("/api/positions", json={"ticker": "AAPL", "side": "long"})
    assert r.status_code == 201, r.text
    assert r.json()["entry_price"] == 150.0   # most recent stored close


def test_close_defaults_exit_to_last_close(client):
    pid = client.post("/api/positions", json={
        "ticker": "AAPL", "entry_price": 140.0,
    }).json()["id"]
    r = client.patch(f"/api/positions/{pid}", json={"close": True})
    assert r.status_code == 200
    body = r.json()
    assert body["exit_price"] == 150.0
    assert body["realized_pct"] == pytest.approx((150.0 - 140.0) / 140.0 * 100.0)


def test_open_404_unknown_ticker(client):
    r = client.post("/api/positions", json={"ticker": "MISSING", "entry_price": 10.0})
    assert r.status_code == 404


def test_open_422_no_price_available(client, db):
    """Ticker without OHLCV bars and no live quote → explicit 422, not a 500."""
    db.add(Stock(ticker="BARE", exchange="NMS", name="Bare")); db.commit()
    r = client.post("/api/positions", json={"ticker": "BARE"})
    assert r.status_code == 422


def test_open_validates_side_and_prices(client):
    r = client.post("/api/positions", json={"ticker": "AAPL", "side": "sideways"})
    assert r.status_code == 422
    r = client.post("/api/positions", json={"ticker": "AAPL", "entry_price": -1.0})
    assert r.status_code == 422
    # Incoherent stop/target order for the side → service-level 422.
    r = client.post("/api/positions", json={
        "ticker": "AAPL", "side": "long", "entry_price": 150.0,
        "stop_price": 170.0, "target_price": 160.0,
    })
    assert r.status_code == 422


def test_list_validates_status(client):
    r = client.get("/api/positions?status=pending")
    assert r.status_code == 422


def test_patch_and_delete_404(client):
    assert client.patch("/api/positions/9999", json={"stop_price": 1.0}).status_code == 404
    assert client.patch("/api/positions/9999", json={"close": True, "exit_price": 1.0}).status_code == 404
    assert client.delete("/api/positions/9999").status_code == 404


def test_alert_id_round_trips(client, db):
    """alert_id links the position to the originating playbook alert."""
    from app.models import Alert
    stock = db.query(Stock).filter_by(ticker="AAPL").one()
    a = Alert(stock_id=stock.id, trigger_price=150.0, snapshot="{}")
    db.add(a); db.commit()
    r = client.post("/api/positions", json={
        "ticker": "AAPL", "entry_price": 150.0, "alert_id": a.id,
    })
    assert r.status_code == 201
    assert r.json()["alert_id"] == a.id


def test_short_position_pnl_via_api(client, db):
    """Short P&L inverted end-to-end (service seam already unit-tested)."""
    pid = client.post("/api/positions", json={
        "ticker": "AAPL", "side": "short", "entry_price": 160.0, "size": 2.0,
    }).json()["id"]
    rows = position_service.list_positions(db, "open", price_fn=lambda t: 150.0)
    row = next(x for x in rows if x["id"] == pid)
    assert row["unrealized_pct"] == pytest.approx(6.25)
    assert row["unrealized_abs"] == pytest.approx(20.0)
