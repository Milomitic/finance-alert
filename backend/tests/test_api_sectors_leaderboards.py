"""GET /api/sectors/leaderboards — the Top-pick strip on the Esplora page.

The service-level behaviour (what each board means, how the analyst rank
avoids becoming a volatility filter) is covered in
`test_leaderboard_service.py`. What matters HERE is the wiring: that the
payload reaches the UI in the shape it expects, that the window is stated
rather than hard-coded client-side, and — the one with history in this repo —
that a score recompute invalidates the cache instead of serving stale picks.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Stock, StockScore, TechnicalScore, User
from app.services import leaderboard_service, sectors_overview_cache

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fresh_cache():
    sectors_overview_cache.clear_overview_cache()
    yield
    sectors_overview_cache.clear_overview_cache()


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
def cache(monkeypatch):
    """Populated stand-in for the fundamentals L1 cache — see the same fixture
    in test_leaderboard_service for why it must not start empty."""
    fake: dict = {"__warm__": None}
    monkeypatch.setattr("app.services.stock_fundamentals_service._CACHE", fake)
    return fake


def _stock(db: Session, ticker: str, *, quality=70.0, technical=75.0) -> Stock:
    s = Stock(
        ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
        sector="Technology", country="US", instrument_type="equity",
    )
    db.add(s)
    db.flush()
    if quality is not None:
        db.add(StockScore(
            stock_id=s.id, composite=quality, risk_tier="moderate",
            breakdown="{}", computed_at=NOW,
        ))
    if technical is not None:
        db.add(TechnicalScore(
            stock_id=s.id, composite=technical, posture="Neutro",
            breakdown="{}", computed_at=NOW,
        ))
    db.commit()
    return s


def _alert(db: Session, stock: Stock, *, tone="bull", detector="rsi_oversold") -> None:
    db.add(Alert(
        stock_id=stock.id, signal_name=detector, trigger_price=100.0,
        triggered_at=datetime.now(UTC) - timedelta(days=1),
        snapshot=json.dumps({"tone": tone}),
    ))
    db.commit()


def _fund(*, mean, current, rec, n):
    return SimpleNamespace(
        micro=SimpleNamespace(recommendation_mean=rec, number_of_analyst_opinions=n),
        price_target=SimpleNamespace(mean=mean, current=current),
    )


class TestPayloadShape:
    def test_returns_the_three_boards_and_the_window(self, client, db, cache):
        _stock(db, "AAA")
        body = client.get("/api/sectors/leaderboards").json()

        assert set(body) == {"analysts", "combined", "signals", "signal_window_days"}
        # Stated by the server so the UI never hard-codes a number that drifts
        # when SIGNAL_WINDOW_DAYS changes.
        assert body["signal_window_days"] == leaderboard_service.SIGNAL_WINDOW_DAYS

    def test_combined_rows_carry_what_the_card_renders(self, client, db, cache):
        _stock(db, "AAA", quality=72.0, technical=88.0)
        row = client.get("/api/sectors/leaderboards").json()["combined"][0]

        assert row["ticker"] == "AAA"
        assert row["name"] == "AAA Inc"
        assert row["sector"] == "Technology"
        assert row["quality"] == 72.0 and row["technical"] == 88.0
        assert row["detail"]  # the card shows a one-line explanation

    def test_analyst_rows_carry_the_numbers_behind_the_rank(self, client, db, cache):
        _stock(db, "AAA")
        cache["AAA"] = _fund(mean=130.0, current=100.0, rec=1.4, n=25)
        row = client.get("/api/sectors/leaderboards").json()["analysts"][0]

        assert row["upside_pct"] == pytest.approx(30.0)
        assert row["analysts"] == 25
        assert row["recommendation"] == 1.4
        assert (row["target"], row["last_close"]) == (130.0, 100.0)

    def test_signals_board_reports_the_bull_bear_split(self, client, db, cache):
        s = _stock(db, "AAA")
        _alert(db, s, tone="bull")
        _alert(db, s, tone="bull", detector="macd_cross")
        row = client.get("/api/sectors/leaderboards").json()["signals"][0]

        assert (row["signals_bull"], row["signals_bear"]) == (2, 0)
        assert row["detectors_bull"] == 2


class TestLimit:
    def test_limit_is_honoured(self, client, db, cache):
        for i in range(8):
            _stock(db, f"S{i}", quality=50.0 + i, technical=50.0 + i)
        body = client.get("/api/sectors/leaderboards?limit=3").json()
        assert len(body["combined"]) == 3

    @pytest.mark.parametrize("limit", [0, 21, -1])
    def test_out_of_range_limits_are_rejected(self, client, db, cache, limit):
        assert client.get(f"/api/sectors/leaderboards?limit={limit}").status_code == 422


class TestCaching:
    def test_a_recompute_invalidates_the_picks(self, client, db, cache):
        """The phantom this repo keeps re-learning.

        The boards rank on composites. Without the shared invalidation hook a
        user who clicks "Ricalcola score" and lands on Esplora inside the 60s
        TTL sees the pre-recompute picks next to post-recompute sector
        averages — the page contradicting itself. `clear_overview_cache`
        drops EVERY key for exactly this reason.
        """
        s = _stock(db, "AAA", quality=50.0, technical=50.0)
        first = client.get("/api/sectors/leaderboards").json()["combined"][0]
        assert first["value"] == pytest.approx(50.0)

        db.query(StockScore).filter(StockScore.stock_id == s.id).update({"composite": 90.0})
        db.query(TechnicalScore).filter(TechnicalScore.stock_id == s.id).update(
            {"composite": 90.0}
        )
        db.commit()

        # Still cached — the TTL has not elapsed.
        assert client.get("/api/sectors/leaderboards").json()["combined"][0]["value"] == 50.0

        sectors_overview_cache.clear_overview_cache()  # what recompute_all calls
        assert client.get("/api/sectors/leaderboards").json()["combined"][0]["value"] == 90.0

    def test_different_limits_do_not_share_a_cache_entry(self, client, db, cache):
        for i in range(8):
            _stock(db, f"S{i}", quality=50.0 + i, technical=50.0 + i)

        assert len(client.get("/api/sectors/leaderboards?limit=2").json()["combined"]) == 2
        assert len(client.get("/api/sectors/leaderboards?limit=5").json()["combined"]) == 5


class TestDegradesGracefully:
    def test_a_cold_fundamentals_cache_empties_one_board_not_the_page(
        self, client, db, cache
    ):
        _stock(db, "AAA", quality=70.0, technical=75.0)
        body = client.get("/api/sectors/leaderboards").json()

        assert body["analysts"] == []
        assert [r["ticker"] for r in body["combined"]] == ["AAA"]

    def test_an_empty_universe_returns_empty_boards_not_an_error(self, client, db, cache):
        body = client.get("/api/sectors/leaderboards").json()
        assert body["analysts"] == body["combined"] == body["signals"] == []
