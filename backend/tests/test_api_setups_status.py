"""GET /api/setups?status=… — the closed setups had nowhere to be seen.

A resolved setup is the only record of whether the feature works: the
conversion rate and the lead time both come from those rows. The endpoint
returned live ones only, so the page could show 1,420 things waiting and
nothing that had ever finished.
"""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.models.stock_setup import (
    STATUS_ACTIVE,
    STATUS_CONVERTED,
    STATUS_EXPIRED,
    StockSetup,
)

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _setup(db, ticker, status, *, resolved_days_ago=None, lead=None, shortlisted=True):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    db.add(StockSetup(
        stock_id=s.id, detector="trend_pullback", tone="bull",
        proximity=0.8, convenience=70.0, missing="attesa", factors_json="{}",
        annotations_json="{}", status=status, shortlisted=shortlisted,
        first_seen_at=NOW - timedelta(days=10), last_seen_at=NOW,
        resolved_at=None if resolved_days_ago is None else NOW - timedelta(days=resolved_days_ago),
        lead_days=lead,
    ))
    db.commit()


def _tickers(client, **params):
    r = client.get("/api/setups", params=params)
    assert r.status_code == 200, r.text
    return [s["ticker"] for s in r.json()["setups"]]


class TestStatusFilter:
    def test_active_is_the_default_and_unchanged(self, client, db):
        _setup(db, "LIVE", STATUS_ACTIVE)
        _setup(db, "DONE", STATUS_CONVERTED, resolved_days_ago=1, lead=6)
        assert _tickers(client) == ["LIVE"]

    @pytest.mark.parametrize("status,expected", [
        (STATUS_CONVERTED, ["DONE"]),
        (STATUS_EXPIRED, ["GONE"]),
    ])
    def test_each_closed_status_can_be_asked_for(self, client, db, status, expected):
        _setup(db, "LIVE", STATUS_ACTIVE)
        _setup(db, "DONE", STATUS_CONVERTED, resolved_days_ago=1, lead=6)
        _setup(db, "GONE", STATUS_EXPIRED, resolved_days_ago=2)
        assert _tickers(client, status=status) == expected

    def test_closed_returns_both_outcomes(self, client, db):
        """Converted and expired together, because the honest reading of the
        feature is the ratio between them, not either one alone."""
        _setup(db, "LIVE", STATUS_ACTIVE)
        _setup(db, "DONE", STATUS_CONVERTED, resolved_days_ago=1, lead=6)
        _setup(db, "GONE", STATUS_EXPIRED, resolved_days_ago=2)
        assert sorted(_tickers(client, status="closed")) == ["DONE", "GONE"]

    def test_closed_rows_are_newest_first(self, client, db):
        _setup(db, "OLD", STATUS_EXPIRED, resolved_days_ago=9)
        _setup(db, "NEW", STATUS_CONVERTED, resolved_days_ago=1, lead=4)
        assert _tickers(client, status="closed") == ["NEW", "OLD"]

    def test_an_unknown_status_is_rejected(self, client, db):
        assert client.get("/api/setups", params={"status": "bogus"}).status_code == 422


class TestOutcomeFields:
    def test_a_converted_row_carries_its_lead_time(self, client, db):
        _setup(db, "DONE", STATUS_CONVERTED, resolved_days_ago=1, lead=6)
        row = client.get("/api/setups", params={"status": "converted"}).json()["setups"][0]
        assert row["status"] == "converted"
        assert row["lead_days"] == 6
        assert row["resolved_at"] is not None

    def test_an_active_row_has_no_outcome(self, client, db):
        _setup(db, "LIVE", STATUS_ACTIVE)
        row = client.get("/api/setups").json()["setups"][0]
        assert row["status"] == "active"
        assert row["resolved_at"] is None and row["lead_days"] is None


class TestShortlist:
    def test_closed_rows_ignore_the_shortlist(self, client, db):
        """The shortlist ranks LIVE candidates. Applying it to history would
        hide outcomes for no reason — and those are exactly the rows that say
        whether the feature earns its place."""
        _setup(db, "GONE", STATUS_EXPIRED, resolved_days_ago=1, shortlisted=False)
        assert _tickers(client, status="closed") == ["GONE"]

    def test_active_rows_still_respect_it(self, client, db):
        _setup(db, "HIDDEN", STATUS_ACTIVE, shortlisted=False)
        _setup(db, "SHOWN", STATUS_ACTIVE, shortlisted=True)
        assert _tickers(client) == ["SHOWN"]
