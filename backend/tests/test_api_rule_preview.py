"""Tests for /api/rules/preview endpoint."""
from datetime import date, timedelta

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
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict:
    # Auth is bypassed via dependency override in `client` fixture; no headers needed.
    return {}


def _seed_oversold_stock(db: Session, ticker: str = "PVTEST.MI") -> int:
    s = Stock(ticker=ticker, name="Preview Test", exchange="BIT", currency="EUR")
    db.add(s)
    db.commit()
    db.refresh(s)
    base = date(2025, 1, 1)
    for i in range(40):
        c = 100.0 - i * 0.5
        db.add(OhlcvDaily(stock_id=s.id, date=base + timedelta(days=i),
                          open=c, high=c, low=c, close=c, volume=1000))
    db.commit()
    return s.id


def test_preview_requires_auth(db: Session) -> None:
    # Use a fresh client with NO dependency overrides — auth must fail
    raw_client = TestClient(app, raise_server_exceptions=False)
    resp = raw_client.post(
        "/api/rules/preview",
        json={"ticker": "X", "expression": {"op": "atomic", "kind": "rsi_oversold", "params": {}}},
    )
    assert resp.status_code == 401


def test_preview_returns_matched_for_oversold(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    _seed_oversold_stock(db, "PVTEST.MI")
    resp = client.post(
        "/api/rules/preview",
        headers=auth_headers,
        json={
            "ticker": "PVTEST.MI",
            "expression": {"op": "atomic", "kind": "rsi_oversold",
                           "params": {"period": 14, "threshold": 30}},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["snapshot"]["op"] == "atomic"
    assert "snapshot" in body["snapshot"]


def test_preview_unknown_ticker_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/rules/preview",
        headers=auth_headers,
        json={
            "ticker": "DOES_NOT_EXIST",
            "expression": {"op": "atomic", "kind": "rsi_oversold", "params": {}},
        },
    )
    assert resp.status_code == 404


def test_preview_invalid_expression_returns_422(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    _seed_oversold_stock(db, "PVTEST2.MI")
    resp = client.post(
        "/api/rules/preview",
        headers=auth_headers,
        json={
            "ticker": "PVTEST2.MI",
            "expression": {"op": "atomic", "kind": "DOES_NOT_EXIST", "params": {}},
        },
    )
    assert resp.status_code == 422
