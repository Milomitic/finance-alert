"""Screener features (lane SCR-2): filter-options visibility guard,
score trend Δ7g from score_history, filter symmetry (pillar max /
vol_ratio_min / pct_off_high) and the global price-alerts listing.
"""
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import PriceAlert, ScoreHistory, Stock, StockMetrics, StockScore, User
from app.services.stock_service import StockFilter, search_stocks

NOW = datetime.now(UTC)


def _stock(db: Session, ticker: str, **kw) -> Stock:
    s = Stock(ticker=ticker, exchange=kw.pop("exchange", "NASDAQ"),
              name=kw.pop("name", f"{ticker} Corp"), country=kw.pop("country", "US"), **kw)
    db.add(s)
    db.flush()
    return s


def _score(db: Session, stock_id: int, composite: float, **pillars) -> None:
    db.add(StockScore(
        stock_id=stock_id, composite=composite, risk_tier="moderate",
        computed_at=NOW, breakdown="{}", **pillars,
    ))


def _metrics(db: Session, stock_id: int, **kw) -> None:
    db.add(StockMetrics(stock_id=stock_id, computed_at=NOW, **kw))


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── 1. Filter options hide catalog-only countries/exchanges ───────────

def test_filter_options_exclude_hidden_countries_and_exchanges(
    client: TestClient, db: Session,
) -> None:
    """CN/JP/KR names on non-surfaced exchanges live in the catalog only for
    breadth — the dropdowns must not offer them (country CN/JP/KR, exchange
    JPX/KRX would always yield 0 results). CN names on HKEX stay visible."""
    _stock(db, "AAPL", exchange="NASDAQ", country="US", sector="Information Technology")
    _stock(db, "600519.SS", exchange="SSE", country="CN", sector="Consumer Staples")
    _stock(db, "7203.T", exchange="JPX", country="JP", sector="Consumer Discretionary")
    _stock(db, "005930.KS", exchange="KRX", country="KR", sector="Information Technology")
    # HKEX listing of a CN company — surfaced exchange, must stay offered.
    _stock(db, "0700.HK", exchange="HKEX", country="CN", sector="Communication Services")
    db.commit()

    r = client.get("/api/stocks/filters")
    assert r.status_code == 200
    data = r.json()
    # Hidden exchanges gone; surfaced ones present.
    assert "JPX" not in data["exchanges"]
    assert "KRX" not in data["exchanges"]
    assert "SSE" not in data["exchanges"]
    assert "HKEX" in data["exchanges"]
    assert "NASDAQ" in data["exchanges"]
    # JP/KR countries gone (only hidden-exchange listings); CN survives via
    # the HKEX row — selecting it returns >0 results, coherent with search.
    assert "JP" not in data["countries"]
    assert "KR" not in data["countries"]
    assert "CN" in data["countries"]
    # Sectors owned exclusively by hidden rows disappear too.
    assert "Consumer Staples" not in data["sectors"]
    assert "Communication Services" in data["sectors"]


# ── 2. Score trend: composite_delta_7d ────────────────────────────────

def _history(db: Session, stock_id: int, days_ago: int, composite: float) -> None:
    db.add(ScoreHistory(
        stock_id=stock_id, lens="qualita",
        captured_on=date.today() - timedelta(days=days_ago),
        composite=composite, pillars="{}",
    ))


def test_composite_delta_7d_uses_latest_capture_at_least_7d_old(db: Session) -> None:
    s = _stock(db, "AAA")
    _score(db, s.id, composite=58.0)
    # Baseline = the LATEST capture ≥ 7 days back (10d ago, 50) — NOT the
    # fresher 3d-ago snapshot and not the older 20d one.
    _history(db, s.id, days_ago=20, composite=40.0)
    _history(db, s.id, days_ago=10, composite=50.0)
    _history(db, s.id, days_ago=3, composite=60.0)
    db.commit()

    page = search_stocks(db, StockFilter())
    assert len(page.items) == 1
    assert page.items[0].score.composite_delta_7d == pytest.approx(8.0)


def test_composite_delta_7d_null_safe_on_thin_history(db: Session) -> None:
    # No history at all → None; only recent (<7d) history → None; history
    # but no current score → None. None of these may 500 or produce 0.0.
    s_none = _stock(db, "BBB")
    _score(db, s_none.id, composite=55.0)

    s_recent = _stock(db, "CCC")
    _score(db, s_recent.id, composite=61.0)
    _history(db, s_recent.id, days_ago=2, composite=59.0)

    s_unscored = _stock(db, "DDD")
    _history(db, s_unscored.id, days_ago=10, composite=44.0)
    db.commit()

    page = search_stocks(db, StockFilter(sort_by="ticker"))
    by_ticker = {it.stock.ticker: it for it in page.items}
    assert by_ticker["BBB"].score.composite_delta_7d is None
    assert by_ticker["CCC"].score.composite_delta_7d is None
    assert by_ticker["DDD"].score.composite_delta_7d is None


def test_composite_delta_7d_ignores_tecnico_lens(db: Session) -> None:
    s = _stock(db, "EEE")
    _score(db, s.id, composite=50.0)
    # A tecnico snapshot ≥7d old must NOT be used as the qualita baseline.
    db.add(ScoreHistory(
        stock_id=s.id, lens="tecnico",
        captured_on=date.today() - timedelta(days=10),
        composite=10.0, pillars="{}",
    ))
    db.commit()
    page = search_stocks(db, StockFilter())
    assert page.items[0].score.composite_delta_7d is None


def test_search_is_constant_query_count_with_history(db: Session) -> None:
    """The Δ7g baseline is a compiled LEFT JOIN, not a per-row lookup: the
    whole search must stay at 3 SQL statements (count + page + metrics
    as-of) regardless of how many stocks/history rows are seeded."""
    for i in range(8):
        s = _stock(db, f"Q{i:02d}")
        _score(db, s.id, composite=50.0 + i)
        _history(db, s.id, days_ago=10, composite=45.0)
        _history(db, s.id, days_ago=20, composite=40.0)
    db.commit()

    engine = db.get_bind()
    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        page = search_stocks(db, StockFilter(limit=50))
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert len(page.items) == 8
    assert all(it.score.composite_delta_7d == pytest.approx(it.score.composite - 45.0)
               for it in page.items)
    assert len(statements) == 3, f"expected 3 statements, got:\n" + "\n".join(statements)


def test_composite_delta_7d_serialized_in_api(client: TestClient, db: Session) -> None:
    s = _stock(db, "FFF")
    _score(db, s.id, composite=70.0)
    _history(db, s.id, days_ago=8, composite=65.5)
    db.commit()
    r = client.get("/api/stocks/search?q=FFF")
    assert r.status_code == 200
    assert r.json()["items"][0]["score"]["composite_delta_7d"] == pytest.approx(4.5)


# ── 3. Filter symmetry: pillar maxes ──────────────────────────────────

def test_pillar_max_filters(db: Session) -> None:
    cheap = _stock(db, "LOW")
    _score(db, cheap.id, composite=50.0, value=30.0)
    rich = _stock(db, "HIGH")
    _score(db, rich.id, composite=50.0, value=80.0)
    unscored = _stock(db, "NOS")  # no score row → excluded when a cap is set
    db.commit()

    page = search_stocks(db, StockFilter(value_max=40.0))
    tickers = [it.stock.ticker for it in page.items]
    assert tickers == ["LOW"]
    assert unscored.id not in [it.stock.id for it in page.items]


def test_pillar_min_and_max_combined(db: Session) -> None:
    for t, g in (("G20", 20.0), ("G50", 50.0), ("G90", 90.0)):
        s = _stock(db, t)
        _score(db, s.id, composite=60.0, growth=g)
    db.commit()
    page = search_stocks(db, StockFilter(growth_min=40.0, growth_max=60.0))
    assert [it.stock.ticker for it in page.items] == ["G50"]


def test_pillar_max_api_validation(client: TestClient) -> None:
    # Same [0,100] bar as the mins.
    r = client.get("/api/stocks/search?profitability_max=150")
    assert r.status_code == 422
    r = client.get("/api/stocks/search?sentiment_max=-1")
    assert r.status_code == 422
    r = client.get("/api/stocks/search?growth_max=55")
    assert r.status_code == 200


# ── 3b. vol_ratio_min ─────────────────────────────────────────────────

def test_vol_ratio_min_filter(db: Session) -> None:
    hot = _stock(db, "HOT")
    _metrics(db, hot.id, last_close=10.0, vol_ratio=1.8)
    cold = _stock(db, "COLD")
    _metrics(db, cold.id, last_close=10.0, vol_ratio=0.6)
    nul = _stock(db, "NUL")
    _metrics(db, nul.id, last_close=10.0, vol_ratio=None)
    db.commit()
    page = search_stocks(db, StockFilter(vol_ratio_min=1.5))
    assert [it.stock.ticker for it in page.items] == ["HOT"]


def test_vol_ratio_min_api_rejects_negative(client: TestClient) -> None:
    r = client.get("/api/stocks/search?vol_ratio_min=-2")
    assert r.status_code == 422
    r = client.get("/api/stocks/search?vol_ratio_min=1.5")
    assert r.status_code == 200


# ── 3c. pct_off_high filter + sort ────────────────────────────────────

def _seed_pct_off_high(db: Session) -> None:
    # ATH: on the 52w high (0%); DIP: −10%; DEEP: −40%; NOHI: high NULL.
    a = _stock(db, "ATH")
    _metrics(db, a.id, last_close=100.0, high_252=100.0)
    d = _stock(db, "DIP")
    _metrics(db, d.id, last_close=90.0, high_252=100.0)
    x = _stock(db, "DEEP")
    _metrics(db, x.id, last_close=60.0, high_252=100.0)
    n = _stock(db, "NOHI")
    _metrics(db, n.id, last_close=50.0, high_252=None)
    db.commit()


def test_pct_off_high_range_filter(db: Session) -> None:
    _seed_pct_off_high(db)
    # Pullback screen: tra il 5% e il 20% sotto il massimo.
    page = search_stocks(db, StockFilter(pct_off_high_min=-20.0, pct_off_high_max=-5.0))
    assert [it.stock.ticker for it in page.items] == ["DIP"]
    # NULL high_252 is excluded whenever a bound is set.
    page = search_stocks(db, StockFilter(pct_off_high_min=-100.0))
    assert "NOHI" not in [it.stock.ticker for it in page.items]


def test_pct_off_high_sort_key(db: Session) -> None:
    _seed_pct_off_high(db)
    # DESC = closest to the 52w high first; NULL expression rows last.
    page = search_stocks(db, StockFilter(sort_by="pct_off_high", sort_dir="desc"))
    assert [it.stock.ticker for it in page.items] == ["ATH", "DIP", "DEEP", "NOHI"]
    page = search_stocks(db, StockFilter(sort_by="pct_off_high", sort_dir="asc"))
    assert [it.stock.ticker for it in page.items] == ["DEEP", "DIP", "ATH", "NOHI"]


def test_pct_off_high_sort_via_api(client: TestClient, db: Session) -> None:
    _seed_pct_off_high(db)
    r = client.get("/api/stocks/search?sort_by=pct_off_high&sort_dir=asc")
    assert r.status_code == 200
    assert [it["stock"]["ticker"] for it in r.json()["items"]][:2] == ["DEEP", "DIP"]


# ── 4. Global price-alerts listing (screener bell glyph) ──────────────

def test_list_all_price_alerts_active_only(client: TestClient, db: Session) -> None:
    s1 = _stock(db, "PA1")
    s2 = _stock(db, "PA2")
    s3 = _stock(db, "PA3")
    db.add(PriceAlert(stock_id=s1.id, target_price=100.0, direction="above", enabled=True))
    # Disabled → not active.
    db.add(PriceAlert(stock_id=s2.id, target_price=50.0, direction="below", enabled=False))
    # Already triggered → not active (idempotency marker set).
    db.add(PriceAlert(
        stock_id=s3.id, target_price=10.0, direction="above", enabled=True,
        triggered_at=NOW,
    ))
    db.commit()

    r = client.get("/api/price-alerts")
    assert r.status_code == 200
    rows = r.json()
    assert [a["stock_id"] for a in rows] == [s1.id]

    # active=false returns everything (audit view).
    r = client.get("/api/price-alerts?active=false")
    assert r.status_code == 200
    assert {a["stock_id"] for a in r.json()} == {s1.id, s2.id, s3.id}
