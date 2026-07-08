"""Tests for Alerts API."""
import csv
import io
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, OhlcvDaily, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_alerts(db: Session, n: int = 3, signal_name: str = "volume_breakout") -> list[Alert]:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    db.commit()
    alerts = []
    for i in range(n):
        a = Alert(
            signal_name=signal_name,
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
    assert body["items"][0]["rule_kind"] == "signal:volume_breakout"


def test_list_alerts_filter_by_rule_kind(client: TestClient, db: Session) -> None:
    _seed_alerts(db, n=2, signal_name="volume_breakout")
    resp = client.get("/api/alerts?rule_kind=signal:volume_breakout")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    resp = client.get("/api/alerts?rule_kind=signal:golden_cross")
    assert resp.json()["total"] == 0


def test_list_alerts_default_excludes_archived(client: TestClient, db: Session) -> None:
    alerts = _seed_alerts(db, n=2)
    alerts[0].archived_at = datetime.now(UTC)
    db.commit()
    resp = client.get("/api/alerts")
    assert resp.json()["total"] == 1


def test_patch_archives(client: TestClient, db: Session) -> None:
    alerts = _seed_alerts(db, n=1)
    resp = client.patch(f"/api/alerts/{alerts[0].id}", json={"archived": True})
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None


def test_bulk_archive(client: TestClient, db: Session) -> None:
    alerts = _seed_alerts(db, n=3)
    ids = [a.id for a in alerts]
    resp = client.post("/api/alerts/bulk", json={"ids": ids, "action": "archive"})
    assert resp.status_code == 200
    assert resp.json()["affected"] == 3
    db.expire_all()
    for a in db.query(Alert).all():
        assert a.archived_at is not None


# Modernised export header: two-score model (tone/strength/probability) +
# signal_date + realised outcome; the dead read_at axis is gone.
_EXPORT_HEADER = [
    "id",
    "triggered_at",
    "signal_date",
    "ticker",
    "rule_kind",
    "trigger_price",
    "tone",
    "strength",
    "probability",
    "outcome_hit",
    "outcome_fwd_return",
    "outcome_horizon_days",
    "outcome_mkt_excess",
    "archived_at",
]


def test_export_csv(client: TestClient, db: Session) -> None:
    _seed_alerts(db, n=2)
    resp = client.get("/api/alerts/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows[0] == _EXPORT_HEADER
    assert len(rows) == 3  # header + 2 alerts


def test_export_csv_snapshot_columns(client: TestClient, db: Session) -> None:
    """tone/strength/probability come from the snapshot JSON; legacy rows with
    confidence-only snapshots fall back to confidence for the strength column."""
    stock = Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft")
    db.add(stock)
    db.commit()
    db.add(
        Alert(
            signal_name="volume_breakout",
            stock_id=stock.id,
            trigger_price=100.0,
            signal_date=date(2026, 7, 1),
            snapshot='{"tone": "bull", "strength": 82, "probability": 54}',
        )
    )
    db.add(
        Alert(
            signal_name="oversold_reversal",
            stock_id=stock.id,
            trigger_price=90.0,
            snapshot='{"tone": "bear", "confidence": 65}',  # legacy pre-split row
        )
    )
    db.commit()
    resp = client.get("/api/alerts/export.csv")
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.text)))
    by_kind = {r[4]: r for r in rows[1:]}
    modern = by_kind["signal:volume_breakout"]
    assert modern[2] == "2026-07-01"  # signal_date
    assert modern[6] == "bull"
    assert modern[7] == "82"
    assert modern[8] == "54"
    legacy = by_kind["signal:oversold_reversal"]
    assert legacy[2] == ""            # no signal_date on legacy rows
    assert legacy[6] == "bear"
    assert legacy[7] == "65"          # strength falls back to confidence
    assert legacy[8] == ""            # no probability pre-split


def test_export_csv_respects_filters(client: TestClient, db: Session) -> None:
    """The export accepts the same filter surface as the list endpoint —
    q / tone / strength_min / probability_min / nature included (audit
    2026-07-08: the page sent them but the endpoint dropped them)."""
    stock_a = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    stock_b = Stock(ticker="NVDA", exchange="NASDAQ", name="Nvidia")
    db.add_all([stock_a, stock_b])
    db.commit()
    db.add_all(
        [
            Alert(
                signal_name="volume_breakout",
                stock_id=stock_a.id,
                trigger_price=100.0,
                snapshot='{"tone": "bull", "strength": 85, "probability": 55}',
            ),
            Alert(
                signal_name="volume_breakout",
                stock_id=stock_a.id,
                trigger_price=101.0,
                snapshot='{"tone": "bear", "strength": 90, "probability": 52}',
            ),
            Alert(
                signal_name="volume_breakout",
                stock_id=stock_b.id,
                trigger_price=500.0,
                snapshot='{"tone": "bull", "strength": 40, "probability": 48}',
            ),
        ]
    )
    db.commit()

    # tone + strength_min: only the strong AAPL bull row survives.
    resp = client.get("/api/alerts/export.csv?tone=bull&strength_min=80")
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) == 2  # header + 1
    assert rows[1][3] == "AAPL"
    assert rows[1][6] == "bull"

    # q substring search (company name) narrows to NVDA's single row.
    resp = client.get("/api/alerts/export.csv?q=nvid")
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) == 2
    assert rows[1][3] == "NVDA"

    # probability_min filters on the snapshot probability.
    resp = client.get("/api/alerts/export.csv?probability_min=50")
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) == 3  # the 48-probability NVDA row is excluded

    # Invalid tone is rejected with the same 422 the list endpoint returns.
    resp = client.get("/api/alerts/export.csv?tone=sideways")
    assert resp.status_code == 422


def test_scan_accepted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /api/alerts/scan returns 202 immediately; actual scan runs in BackgroundTasks."""
    monkeypatch.setattr("app.api.alerts._run_scan_in_background", lambda _ids: None)
    resp = client.post("/api/alerts/scan", json={})
    assert resp.status_code == 202


def test_scan_stock_signals_returns_counts(client: TestClient, db: Session) -> None:
    """POST /api/alerts/scan-stock/{ticker} runs the engine synchronously over
    stored OHLCV and returns {added, total}."""
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    db.flush()
    base = date(2026, 1, 1)
    price = 100.0
    for i in range(40):
        price += 0.5
        db.add(OhlcvDaily(
            stock_id=stock.id, date=base + timedelta(days=i),
            open=price, high=price + 1, low=price - 1, close=price, volume=1_000_000,
        ))
    db.commit()
    resp = client.post("/api/alerts/scan-stock/AAPL")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "added" in body and "total" in body
    assert body["added"] >= 0 and body["total"] >= 0


def test_scan_stock_signals_insufficient_history_422(client: TestClient, db: Session) -> None:
    stock = Stock(ticker="ZZZ", exchange="NASDAQ", name="Z")
    db.add(stock)
    db.commit()
    resp = client.post("/api/alerts/scan-stock/ZZZ")
    assert resp.status_code == 422


def test_scan_stock_signals_unknown_ticker_404(client: TestClient) -> None:
    resp = client.post("/api/alerts/scan-stock/NOPE")
    assert resp.status_code == 404


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
