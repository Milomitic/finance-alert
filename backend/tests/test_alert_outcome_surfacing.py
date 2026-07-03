"""Tests for the per-alert outcome surfacing (signal_outcomes LEFT JOIN in
list_alerts) + the cache-only next_earnings_date field.

Covers audit findings B3-1 (realized outcomes on the alerts list) and B3-5
(earnings-proximity flag, cache-only — never a network call in the list path).
"""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, SignalOutcome, Stock, User
from app.services import stock_fundamentals_service
from app.services.alert_service import list_alerts
from app.services.stock_fundamentals_service import Fundamentals


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_signal_alert(
    db: Session, ticker: str = "AAPL", *, signal_name: str = "volume_breakout"
) -> Alert:
    stock = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(stock)
    db.flush()
    a = Alert(
        stock_id=stock.id,
        signal_name=signal_name,
        signal_date=date(2026, 5, 4),
        trigger_price=100.0,
        snapshot=json.dumps({"tone": "bull", "strength": 70, "chain": []}),
    )
    db.add(a)
    db.commit()
    return a


def _seed_outcome(db: Session, alert: Alert, **overrides) -> SignalOutcome:
    kwargs = dict(
        alert_id=alert.id,
        stock_id=alert.stock_id,
        detector=alert.signal_name,
        signal_date=alert.signal_date,
        tone="bull",
        horizon_days=21,
        entry_close=100.0,
        forward_close=102.345678,
        fwd_return=0.02345678,
        universe_mean_fwd=0.01,
        mkt_neutral_excess=0.01345678,
        abs_hit=1,
        mkt_neutral_hit=1,
        regime_at_signal="bull",
        strength=70,
        probability=52,
    )
    kwargs.update(overrides)
    o = SignalOutcome(**kwargs)
    db.add(o)
    db.commit()
    return o


# ── outcome join ─────────────────────────────────────────────────────────────

def test_matured_alert_carries_outcome_fields(db: Session) -> None:
    a = _seed_signal_alert(db)
    _seed_outcome(db, a)

    items, total, _ = list_alerts(db)
    assert total == 1
    it = items[0]
    assert it["outcome_hit"] is True
    # Rounded to 4 decimals by the service.
    assert it["outcome_fwd_return"] == 0.0235
    assert it["outcome_horizon_days"] == 21
    assert it["outcome_mkt_excess"] == 0.0135


def test_miss_outcome_maps_to_false(db: Session) -> None:
    a = _seed_signal_alert(db)
    _seed_outcome(
        db, a, abs_hit=0, fwd_return=-0.0312, forward_close=96.88,
        mkt_neutral_excess=None, mkt_neutral_hit=None, universe_mean_fwd=None,
    )

    items, _, _ = list_alerts(db)
    it = items[0]
    assert it["outcome_hit"] is False
    assert it["outcome_fwd_return"] == -0.0312
    # No universe benchmark at maturation → excess stays null.
    assert it["outcome_mkt_excess"] is None


def test_pending_alert_has_all_null_outcome(db: Session) -> None:
    _seed_signal_alert(db)  # no SignalOutcome row → not yet matured

    items, total, _ = list_alerts(db)
    assert total == 1
    it = items[0]
    assert it["outcome_hit"] is None
    assert it["outcome_fwd_return"] is None
    assert it["outcome_horizon_days"] is None
    assert it["outcome_mkt_excess"] is None


def test_outcome_join_does_not_fan_out_pagination(db: Session) -> None:
    """One outcome row per alert (unique alert_id) — total must equal the
    number of alerts, matured or not."""
    a1 = _seed_signal_alert(db, "AAA")
    _seed_signal_alert(db, "BBB")
    _seed_outcome(db, a1)

    items, total, has_more = list_alerts(db)
    assert total == 2
    assert len(items) == 2
    assert has_more is False


def test_api_list_alerts_exposes_outcome_fields(client: TestClient, db: Session) -> None:
    a = _seed_signal_alert(db)
    _seed_outcome(db, a)

    body = client.get("/api/alerts").json()
    it = body["items"][0]
    assert it["outcome_hit"] is True
    assert it["outcome_fwd_return"] == 0.0235
    assert it["outcome_horizon_days"] == 21
    assert it["outcome_mkt_excess"] == 0.0135


# ── next_earnings_date (cache-only) ──────────────────────────────────────────

def test_next_earnings_date_from_warm_cache(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_signal_alert(db, "AAPL")
    monkeypatch.setattr(
        stock_fundamentals_service,
        "_CACHE",
        {"AAPL": Fundamentals(ticker="AAPL", next_earnings_date="2026-07-20")},
    )

    items, _, _ = list_alerts(db)
    assert items[0]["next_earnings_date"] == date(2026, 7, 20)


def test_next_earnings_date_null_on_cold_cache_and_no_network(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cold cache → null, and the list path must NEVER trigger an upstream
    fundamentals fetch (the calendar-service cache-only contract)."""
    _seed_signal_alert(db, "MSFT")
    monkeypatch.setattr(stock_fundamentals_service, "_CACHE", {})

    def _boom(*_a, **_k):  # pragma: no cover - fails the test if reached
        raise AssertionError("list_alerts must not call get_fundamentals")

    monkeypatch.setattr(stock_fundamentals_service, "get_fundamentals", _boom)

    items, _, _ = list_alerts(db)
    assert items[0]["next_earnings_date"] is None


def test_next_earnings_date_unparsable_is_null(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_signal_alert(db, "NVDA")
    monkeypatch.setattr(
        stock_fundamentals_service,
        "_CACHE",
        {"NVDA": Fundamentals(ticker="NVDA", next_earnings_date="not-a-date")},
    )

    items, _, _ = list_alerts(db)
    assert items[0]["next_earnings_date"] is None


def test_api_next_earnings_date_serialized(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_signal_alert(db, "AAPL")
    monkeypatch.setattr(
        stock_fundamentals_service,
        "_CACHE",
        {"AAPL": Fundamentals(ticker="AAPL", next_earnings_date="2026-07-20")},
    )

    body = client.get("/api/alerts").json()
    assert body["items"][0]["next_earnings_date"] == "2026-07-20"
