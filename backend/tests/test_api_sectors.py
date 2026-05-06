"""Tests for Sectors API.

Smoke coverage for /api/sectors and /api/sectors/{name}/detail. The
endpoints touch quite a few moving parts (visibility filter, score
join, fundamentals fetch, percentile aggregations) so it's easy to
regress on attribute renames. These tests catch the kind of bug
"AttributeError: 'Stock' object has no attribute 'company_name'"
that slipped through pre-launch.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, StockScore, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_sector(db: Session, sector: str = "Technology", n: int = 3, prefix: str | None = None) -> None:
    """Seed n stocks in `sector` with simple StockScore rows."""
    # Derive a ticker prefix from the sector name so sequential tests
    # in the same DB session don't collide on (ticker, exchange).
    pfx = prefix or (sector[:3].upper().replace(" ", ""))
    for i in range(n):
        st = Stock(
            ticker=f"{pfx}{i}",
            exchange="NASDAQ",
            name=f"Test {i}",
            sector=sector,
            country="US",
            market_cap=10_000_000_000 + i * 1_000_000,
        )
        db.add(st)
        db.flush()
        sc = StockScore(
            stock_id=st.id,
            composite=70.0 - i,
            quality=70.0,
            growth=60.0,
            value=50.0,
            momentum=80.0,
            sentiment=60.0,
            risk_tier="moderate",
            breakdown="{}",
            computed_at=__import__('datetime').datetime.now(__import__('datetime').UTC),
        )
        db.add(sc)
    db.commit()


def test_list_sectors_basic(client: TestClient, db: Session) -> None:
    _seed_sector(db, "Technology", 4)
    _seed_sector(db, "Healthcare", 2)
    resp = client.get("/api/sectors")
    assert resp.status_code == 200
    body = resp.json()
    names = {s["name"] for s in body}
    assert "Technology" in names
    assert "Healthcare" in names
    tech = next(s for s in body if s["name"] == "Technology")
    assert tech["stock_count"] == 4
    assert tech["avg_score"] is not None


def test_sector_detail_basic(client: TestClient, db: Session) -> None:
    _seed_sector(db, "Technology", 6)
    resp = client.get("/api/sectors/Technology/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sector"] == "Technology"
    assert body["kpis"]["stock_count"] == 6
    # All seeded scores >0, so distribution should have entries above 60
    assert sum(body["kpis"]["score_distribution"]) == 6
    assert len(body["top_picks"]) == 5  # top 5 even if 6 stocks
    # bottom_picks is populated only when len > 5
    assert len(body["bottom_picks"]) == 5
    # Highest score (composite=70) should be at top
    assert body["top_picks"][0]["composite"] == 70.0


def test_sector_detail_unknown_returns_404(client: TestClient, db: Session) -> None:
    resp = client.get("/api/sectors/NotARealSector/detail")
    assert resp.status_code == 404


def test_sector_detail_returns_stock_attribute_name(client: TestClient, db: Session) -> None:
    """Regression: 'Stock' has .name not .company_name. The detail
    endpoint reads stock.name when building rows; this test verifies
    that the field round-trips through Pydantic without an attribute
    error."""
    _seed_sector(db, "Industrials", 2)
    resp = client.get("/api/sectors/Industrials/detail")
    assert resp.status_code == 200
    body = resp.json()
    # The seeded stocks have name="Test 0", "Test 1"
    names = {row["name"] for row in body["stocks"]}
    assert names == {"Test 0", "Test 1"}


def test_sector_detail_url_encoded(client: TestClient, db: Session) -> None:
    """Sector names with spaces (e.g. 'Consumer Discretionary') round-trip
    through URL encoding. Real-world bug: encoding ate the space."""
    _seed_sector(db, "Consumer Discretionary", 3)
    resp = client.get("/api/sectors/Consumer%20Discretionary/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sector"] == "Consumer Discretionary"
    assert body["kpis"]["stock_count"] == 3
