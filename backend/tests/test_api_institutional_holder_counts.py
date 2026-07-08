"""Tests for GET /api/institutionals/holder-counts (smart-money badge).

Aggregation contract:
- counts DISTINCT funds holding the ticker in their LATEST filing only
  (an older filing's holdings never leak into the count);
- sold_out phantom rows (shares == 0) are not holders;
- stale funds (latest period older than the 18-month cutoff) are excluded;
- tickers with zero holders are OMITTED from the response;
- duplicate / blank tickers in the query string are tolerated.

Auth: 401 without cookie, 200 with override (router convention).
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import (
    Institutional,
    InstitutionalFiling,
    InstitutionalHolding,
    User,
)
from app.services import institutional_service

TODAY = date.today()
FRESH_Q = TODAY - timedelta(days=60)          # recent quarter end
PREV_Q = TODAY - timedelta(days=150)          # the quarter before it
STALE_Q = TODAY - timedelta(days=700)         # > 18-month freshness cutoff


def _inst(db: Session, slug: str, *, type_: str = "superinvestor") -> Institutional:
    row = Institutional(
        slug=slug, name=slug.title(), type=type_, source="dataroma",
    )
    db.add(row)
    db.flush()
    return row


def _filing(db: Session, inst: Institutional, period_end: date) -> InstitutionalFiling:
    row = InstitutionalFiling(
        institutional_id=inst.id, period_end_date=period_end,
    )
    db.add(row)
    db.flush()
    return row


def _holding(
    db: Session,
    filing: InstitutionalFiling,
    ticker: str,
    *,
    shares: int | None = 1_000,
    action: str | None = None,
) -> InstitutionalHolding:
    row = InstitutionalHolding(
        filing_id=filing.id, ticker=ticker, shares=shares,
        value_usd=1_000_000, portfolio_pct=1.0, action=action,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded_db(db: Session) -> Session:
    """Three funds:

    - fund-a: two filings. PREV_Q held AAPL+MSFT; FRESH_Q (latest) holds
      AAPL and carries a sold_out phantom row for MSFT (shares=0).
    - fund-b: one FRESH_Q filing holding AAPL + GOOG (GOOG with NULL
      shares — Dataroma rows without a share count still count).
    - fund-c: STALE fund (latest filing 700 days old) holding AAPL —
      must NOT count.

    Expected counts: AAPL=2 (a+b), GOOG=1 (b), MSFT absent (sold out),
    NFLX absent (nobody holds it).
    """
    a = _inst(db, "fund-a")
    a_prev = _filing(db, a, PREV_Q)
    _holding(db, a_prev, "AAPL")
    _holding(db, a_prev, "MSFT")
    a_latest = _filing(db, a, FRESH_Q)
    _holding(db, a_latest, "AAPL", action="hold")
    _holding(db, a_latest, "MSFT", shares=0, action="sold_out")

    b = _inst(db, "fund-b", type_="hedge_fund")
    b_latest = _filing(db, b, FRESH_Q)
    _holding(db, b_latest, "AAPL", action="add")
    _holding(db, b_latest, "GOOG", shares=None)

    c = _inst(db, "fund-c")
    c_latest = _filing(db, c, STALE_Q)
    _holding(db, c_latest, "AAPL")

    db.commit()
    return db


@pytest.fixture
def client(seeded_db: Session) -> TestClient:
    user = User(username="tester", password_hash="x")
    seeded_db.add(user)
    seeded_db.commit()
    app.dependency_overrides[get_db] = lambda: seeded_db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Aggregation semantics
# ---------------------------------------------------------------------------

def test_counts_latest_filings_only_and_omit_zero(client: TestClient):
    resp = client.get(
        "/api/institutionals/holder-counts?tickers=AAPL,MSFT,GOOG,NFLX"
    )
    assert resp.status_code == 200
    data = resp.json()
    # AAPL: fund-a + fund-b (fund-c is stale, doesn't count)
    assert data["AAPL"] == 2
    # GOOG: NULL shares still counts as a holder
    assert data["GOOG"] == 1
    # MSFT: only appears in fund-a's latest filing as sold_out (shares=0)
    # and in the PREVIOUS filing (which must not leak in) → omitted
    assert "MSFT" not in data
    # NFLX: nobody holds it → omitted, not 0
    assert "NFLX" not in data


def test_duplicate_and_blank_tickers_are_tolerated(client: TestClient):
    resp = client.get(
        "/api/institutionals/holder-counts?tickers=AAPL,%20AAPL%20,,GOOG"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"AAPL": 2, "GOOG": 1}


def test_empty_tickers_returns_empty_dict(client: TestClient):
    resp = client.get("/api/institutionals/holder-counts?tickers=,")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_too_many_tickers_returns_422(client: TestClient):
    tickers = ",".join(f"T{i}" for i in range(101))
    resp = client.get(f"/api/institutionals/holder-counts?tickers={tickers}")
    assert resp.status_code == 422


def test_missing_tickers_param_returns_422(client: TestClient):
    resp = client.get("/api/institutionals/holder-counts")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth (router convention: everything behind get_current_user)
# ---------------------------------------------------------------------------

def test_unauthenticated_returns_401(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = TestClient(app).get(
            "/api/institutionals/holder-counts?tickers=AAPL"
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Service-level: stale-fund cutoff is parametrizable
# ---------------------------------------------------------------------------

def test_service_stale_cutoff_configurable(seeded_db: Session):
    # With a giant cutoff even fund-c's 700-day-old filing counts.
    counts = institutional_service.holder_counts_for_tickers(
        seeded_db, ["AAPL"], max_age_months=60
    )
    assert counts["AAPL"] == 3
