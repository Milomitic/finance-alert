"""Lane ESP-2 — Esplora lenses + funnel (audit 2026-07-08).

Behaviors under test on /api/sectors/overview + /{name}/detail:

1. TECNICO: per-sector avg technical composite (+ n) in the overview
   rollup and in the detail KPIs — equity-only, stocks without a
   technical score don't dilute the average.
2. TIME AXIS: (a) per-sector Δ% giornaliero read from the latest market
   snapshot's `sectors` block (snapshot-derived, never recomputed;
   missing/malformed snapshot degrades to None); (b) per-sector Qualità
   score-trend from score_history (qualita lens only, last ~30 capture
   days, ascending).
3. SEGNALI: signals_7d per sector (signal_date window, non-archived,
   bull/bear split via json_extract on the snapshot tone).
4. ETF proxy: static GICS→SPDR map filtered by catalog presence.
5. Cache: the enrichments are memoized together with the overview payload.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import (
    Alert,
    MarketSnapshot,
    ScoreHistory,
    Stock,
    StockScore,
    TechnicalScore,
    User,
)
from app.services import sectors_overview_cache

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures / seeding helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fresh_overview_cache():
    """The overview payload is memoized for 60s process-wide; without the
    reset a prior test's enriched payload would leak into the next."""
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


def _stock(db: Session, ticker: str, *, sector: str | None = "Financials",
           industry: str | None = "Banks", instrument_type: str = "equity",
           composite: float | None = 60.0) -> Stock:
    s = Stock(
        ticker=ticker,
        exchange="NYSE Arca" if instrument_type == "etf" else "NASDAQ",
        name=ticker, sector=sector, industry=industry, country="US",
        market_cap=10_000_000_000, instrument_type=instrument_type,
    )
    db.add(s)
    db.flush()
    if composite is not None:
        db.add(StockScore(
            stock_id=s.id, composite=composite, risk_tier="moderate",
            breakdown="{}", computed_at=NOW,
        ))
    return s


def _tech(db: Session, stock: Stock, composite: float) -> None:
    db.add(TechnicalScore(
        stock_id=stock.id, composite=composite, posture="Neutro",
        breakdown="{}", computed_at=NOW,
    ))


def _alert(db: Session, stock: Stock, *, days_ago: int, tone: str | None = "bull",
           archived: bool = False) -> None:
    snapshot: dict = {"tone": tone} if tone is not None else {}
    db.add(Alert(
        stock_id=stock.id,
        signal_name="rsi_oversold",
        signal_date=date.today() - timedelta(days=days_ago),
        trigger_price=100.0,
        snapshot=json.dumps(snapshot),
        archived_at=NOW if archived else None,
    ))


def _history(db: Session, stock: Stock, captured_on: date, composite: float,
             lens: str = "qualita") -> None:
    db.add(ScoreHistory(
        stock_id=stock.id, lens=lens, captured_on=captured_on,
        composite=composite, pillars="{}",
    ))


def _snapshot(db: Session, sectors: list[dict] | None, *, raw: str | None = None) -> None:
    payload = raw if raw is not None else json.dumps({"sectors": sectors})
    db.merge(MarketSnapshot(
        id=1, computed_at=NOW, stocks_total=10, stocks_with_data=10,
        payload=payload,
    ))


def _overview_sector(client: TestClient, name: str) -> dict:
    body = client.get("/api/sectors/overview").json()
    return next(s for s in body["sectors"] if s["name"] == name)


# ---------------------------------------------------------------------------
# 1. Tecnico per sector
# ---------------------------------------------------------------------------

def test_overview_technical_rollup_avg_and_count(client: TestClient, db: Session):
    a = _stock(db, "JPM")
    b = _stock(db, "BAC")
    _stock(db, "C")            # no technical score → not in the Tecnico avg
    _tech(db, a, 70.0)
    _tech(db, b, 50.0)
    db.commit()

    fin = _overview_sector(client, "Financials")
    assert fin["stock_count"] == 3
    assert fin["technical_count"] == 2       # only scored stocks counted
    assert fin["avg_technical"] == pytest.approx(60.0)


def test_overview_technical_rollup_excludes_etf(client: TestClient, db: Session):
    a = _stock(db, "JPM")
    etf = _stock(db, "SPY", instrument_type="etf", composite=None)
    _tech(db, a, 40.0)
    _tech(db, etf, 99.0)       # must never enter the Financials Tecnico avg
    db.commit()

    fin = _overview_sector(client, "Financials")
    assert fin["technical_count"] == 1
    assert fin["avg_technical"] == pytest.approx(40.0)


def test_overview_sector_without_tech_scores_has_none(client: TestClient, db: Session):
    _stock(db, "JPM")
    db.commit()
    fin = _overview_sector(client, "Financials")
    assert fin["avg_technical"] is None
    assert fin["technical_count"] == 0


def test_detail_kpis_include_technical(client: TestClient, db: Session):
    a = _stock(db, "JPM")
    b = _stock(db, "BAC")
    _stock(db, "C")
    _tech(db, a, 80.0)
    _tech(db, b, 60.0)
    db.commit()

    kpis = client.get("/api/sectors/Financials/detail").json()["kpis"]
    assert kpis["avg_technical"] == pytest.approx(70.0)
    assert kpis["technical_count"] == 2
    assert kpis["stock_count"] == 3


def test_detail_kpis_technical_none_when_unscored(client: TestClient, db: Session):
    _stock(db, "JPM")
    db.commit()
    kpis = client.get("/api/sectors/Financials/detail").json()["kpis"]
    assert kpis["avg_technical"] is None
    assert kpis["technical_count"] == 0


# ---------------------------------------------------------------------------
# 2a. Δ% giornaliero from the market snapshot
# ---------------------------------------------------------------------------

def test_overview_change_pct_read_from_snapshot(client: TestClient, db: Session):
    _stock(db, "JPM")
    _stock(db, "XOM", sector="Energy", industry="Oil & Gas")
    _snapshot(db, [
        {"sector": "Financials", "n_stocks": 5, "avg_change_pct": 1.25,
         "pct_above_ema200": 60.0},
        {"sector": "Energy", "n_stocks": 3, "avg_change_pct": -0.8,
         "pct_above_ema200": 40.0},
    ])
    db.commit()

    body = client.get("/api/sectors/overview").json()
    by_name = {s["name"]: s for s in body["sectors"]}
    assert by_name["Financials"]["change_pct"] == pytest.approx(1.25)
    assert by_name["Energy"]["change_pct"] == pytest.approx(-0.8)


def test_overview_change_pct_none_without_snapshot(client: TestClient, db: Session):
    _stock(db, "JPM")
    db.commit()
    assert _overview_sector(client, "Financials")["change_pct"] is None


def test_overview_change_pct_tolerates_malformed_snapshot(client: TestClient, db: Session):
    """A corrupt payload must degrade to no-Δ%, not 500 the hub page."""
    _stock(db, "JPM")
    _snapshot(db, None, raw="{not valid json")
    db.commit()
    resp = client.get("/api/sectors/overview")
    assert resp.status_code == 200
    fin = next(s for s in resp.json()["sectors"] if s["name"] == "Financials")
    assert fin["change_pct"] is None


# ---------------------------------------------------------------------------
# 2b. Qualità score-trend sparkline from score_history
# ---------------------------------------------------------------------------

def test_overview_score_trend_averages_per_capture_day(client: TestClient, db: Session):
    a = _stock(db, "JPM")
    b = _stock(db, "BAC")
    d1, d2 = date(2026, 7, 1), date(2026, 7, 2)
    _history(db, a, d1, 60.0)
    _history(db, b, d1, 40.0)
    _history(db, a, d2, 70.0)
    _history(db, b, d2, 50.0)
    # Tecnico-lens rows must NOT bleed into the Qualità sparkline.
    _history(db, a, d2, 5.0, lens="tecnico")
    db.commit()

    trend = _overview_sector(client, "Financials")["score_trend"]
    assert [p["date"] for p in trend] == ["2026-07-01", "2026-07-02"]  # ascending
    assert trend[0]["avg"] == pytest.approx(50.0)   # mean(60, 40)
    assert trend[1]["avg"] == pytest.approx(60.0)   # mean(70, 50) — no tecnico 5.0


def test_overview_score_trend_limited_to_last_30_captures(client: TestClient, db: Session):
    a = _stock(db, "JPM")
    start = date(2026, 6, 1)
    for i in range(35):
        _history(db, a, start + timedelta(days=i), 50.0 + i)
    db.commit()

    trend = _overview_sector(client, "Financials")["score_trend"]
    assert len(trend) == 30
    # The window keeps the MOST RECENT 30 capture days: the first 5 drop.
    assert trend[0]["date"] == (start + timedelta(days=5)).isoformat()
    assert trend[-1]["date"] == (start + timedelta(days=34)).isoformat()


def test_overview_score_trend_empty_without_history(client: TestClient, db: Session):
    _stock(db, "JPM")
    db.commit()
    assert _overview_sector(client, "Financials")["score_trend"] == []


# ---------------------------------------------------------------------------
# 3. Segnali per sector (7-day window, tone split)
# ---------------------------------------------------------------------------

def test_overview_signals_7d_counts_and_tone_split(client: TestClient, db: Session):
    a = _stock(db, "JPM")
    b = _stock(db, "XOM", sector="Energy", industry="Oil & Gas")
    _alert(db, a, days_ago=1, tone="bull")
    _alert(db, a, days_ago=3, tone="bear")
    _alert(db, a, days_ago=5, tone="neutral")   # counts in total only
    _alert(db, a, days_ago=10, tone="bull")     # outside the 7g window
    _alert(db, a, days_ago=2, tone="bull", archived=True)  # archived excluded
    _alert(db, b, days_ago=0, tone="bear")
    db.commit()

    body = client.get("/api/sectors/overview").json()
    by_name = {s["name"]: s for s in body["sectors"]}
    fin = by_name["Financials"]
    assert fin["signals_7d"] == 3
    assert fin["signals_7d_bull"] == 1
    assert fin["signals_7d_bear"] == 1
    en = by_name["Energy"]
    assert en["signals_7d"] == 1
    assert en["signals_7d_bear"] == 1


def test_overview_signals_7d_zero_without_alerts(client: TestClient, db: Session):
    _stock(db, "JPM")
    db.commit()
    fin = _overview_sector(client, "Financials")
    assert fin["signals_7d"] == 0
    assert fin["signals_7d_bull"] == 0
    assert fin["signals_7d_bear"] == 0


# ---------------------------------------------------------------------------
# 4. ETF proxy — catalog-checked, never hardcoded truth
# ---------------------------------------------------------------------------

def test_overview_etf_proxy_only_when_in_catalog(client: TestClient, db: Session):
    _stock(db, "JPM")                                    # Financials → XLF
    _stock(db, "XOM", sector="Energy", industry="Oil & Gas")  # Energy → XLE
    # XLF present in the catalog (as an ETF row); XLE deliberately absent.
    _stock(db, "XLF", sector="Financials", industry=None,
           instrument_type="etf", composite=None)
    db.commit()

    body = client.get("/api/sectors/overview").json()
    by_name = {s["name"]: s for s in body["sectors"]}
    assert by_name["Financials"]["etf_proxy"] == "XLF"
    assert by_name["Energy"]["etf_proxy"] is None        # not in catalog → no link


def test_overview_etf_proxy_unmapped_sector_is_none(client: TestClient, db: Session):
    """A non-GICS bucket (e.g. 'Other') has no SPDR proxy by definition."""
    _stock(db, "MISC", sector="Other", industry=None)
    db.commit()
    assert _overview_sector(client, "Other")["etf_proxy"] is None


# ---------------------------------------------------------------------------
# 5. The enrichments live inside the 60s overview cache
# ---------------------------------------------------------------------------

def test_overview_enrichments_are_memoized(client: TestClient, db: Session):
    a = _stock(db, "JPM")
    db.commit()
    first = _overview_sector(client, "Financials")
    assert first["signals_7d"] == 0

    # New alert lands between the two hits → still the memoized payload.
    _alert(db, a, days_ago=0, tone="bull")
    db.commit()
    assert _overview_sector(client, "Financials")["signals_7d"] == 0

    sectors_overview_cache.clear_overview_cache()
    assert _overview_sector(client, "Financials")["signals_7d"] == 1


def test_legacy_list_sectors_still_validates_with_defaults(client: TestClient, db: Session):
    """GET /api/sectors (bare rollup) doesn't pay for the enrichments —
    the new fields come back at their defaults."""
    _stock(db, "JPM")
    db.commit()
    body = client.get("/api/sectors").json()
    fin = next(s for s in body if s["name"] == "Financials")
    assert fin["avg_technical"] is None
    assert fin["signals_7d"] == 0
    assert fin["score_trend"] == []
    assert fin["etf_proxy"] is None
