"""Tests for Alerts API."""
import csv
import io
from datetime import UTC, datetime

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


def _seed_alerts(db: Session, n: int = 3) -> list[Alert]:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    db.commit()
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    alerts = []
    for i in range(n):
        a = Alert(
            rule_id=rule.id,
            stock_id=stock.id,
            trigger_price=100.0 + i,
            snapshot='{"rsi": 28.0}',
        )
        db.add(a)
        alerts.append(a)
    db.commit()
    return alerts


def test_list_alerts_returns_paginated(client: TestClient, db: Session) -> None:
    _seed_alerts(db, n=3)
    resp = client.get("/api/alerts?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["has_more"] is True
    assert body["items"][0]["ticker"] == "AAPL"
    assert body["items"][0]["rule_kind"] == "rsi_oversold"


def test_list_alerts_filter_by_rule_kind(client: TestClient, db: Session) -> None:
    _seed_alerts(db, n=2)
    resp = client.get("/api/alerts?rule_kind=rsi_oversold")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    resp = client.get("/api/alerts?rule_kind=golden_cross")
    assert resp.json()["total"] == 0


def test_list_alerts_default_excludes_archived(client: TestClient, db: Session) -> None:
    alerts = _seed_alerts(db, n=2)
    alerts[0].archived_at = datetime.now(UTC)
    db.commit()
    resp = client.get("/api/alerts")
    assert resp.json()["total"] == 1


def test_patch_marks_read(client: TestClient, db: Session) -> None:
    alerts = _seed_alerts(db, n=1)
    resp = client.patch(f"/api/alerts/{alerts[0].id}", json={"read": True})
    assert resp.status_code == 200
    assert resp.json()["read_at"] is not None


def test_bulk_archive(client: TestClient, db: Session) -> None:
    alerts = _seed_alerts(db, n=3)
    ids = [a.id for a in alerts]
    resp = client.post("/api/alerts/bulk", json={"ids": ids, "action": "archive"})
    assert resp.status_code == 200
    assert resp.json()["affected"] == 3
    db.expire_all()
    for a in db.query(Alert).all():
        assert a.archived_at is not None


def test_unread_count(client: TestClient, db: Session) -> None:
    _seed_alerts(db, n=3)
    resp = client.get("/api/alerts/unread-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


def test_export_csv(client: TestClient, db: Session) -> None:
    _seed_alerts(db, n=2)
    resp = client.get("/api/alerts/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows[0] == [
        "id",
        "triggered_at",
        "ticker",
        "rule_kind",
        "trigger_price",
        "read_at",
        "archived_at",
    ]
    assert len(rows) == 3  # header + 2 alerts


def test_scan_accepted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /api/alerts/scan returns 202 immediately; actual scan runs in BackgroundTasks."""
    monkeypatch.setattr("app.api.alerts._run_scan_in_background", lambda _ids: None)
    resp = client.post("/api/alerts/scan", json={})
    assert resp.status_code == 202


def test_send_digest_endpoint_no_alerts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    resp = client.post("/api/alerts/send-digest", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is False
