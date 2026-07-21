"""Lane F (B4-7) — ETF exclusions + screener surfacing.

Four surfaces, one flag (`stocks.instrument_type = 'etf'`):

1. Qualità scoring: `recompute_all` SKIPS ETFs (no new StockScore row) and
   PURGES any stale row a pre-flag recompute left behind — so ETFs also drop
   out of the sector/universe composite percentiles, which derive from
   stock_scores rows. The single-stock recompute escape hatch is guarded too.
2. Market-neutral benchmark: `_load_universe_closes(exclude_etf=True)` drops
   ETF rows from the universe forward-mean population; per-stock series for
   an ETF's OWN alerts stay loadable (entry/forward math unchanged).
3. Screener: `StockFilter(exclude_etf=True)` + the `exclude_etf` query param;
   `instrument_type` surfaces on the StockOut payload.
4. Metrics as-of: the search response carries `metrics_computed_at` (shared
   computed_at of the last stock_metrics refresh, UTC-tagged).
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.scores import _composite_percentiles
from app.main import app
from app.models import Alert, OhlcvDaily, SignalOutcome, Stock, StockMetrics, StockScore, User
from app.services import (
    score_service,
    stock_fundamentals_service,
    stock_news_service,
)
from app.services import (
    signal_outcome_service as sos,
)
from app.services.stock_fundamentals_service import Fundamentals, MicroData
from app.services.stock_service import StockFilter, search_stocks

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

def _stock(db: Session, ticker: str, *, instrument_type: str = "equity",
           sector: str = "Technology") -> Stock:
    s = Stock(
        ticker=ticker, exchange="NYSE Arca" if instrument_type == "etf" else "NASDAQ",
        name=ticker, sector=sector, country="US",
        market_cap=10_000_000_000, instrument_type=instrument_type,
    )
    db.add(s)
    db.flush()
    return s


def _seed_ohlcv(db: Session, stock_id: int, closes: list[float],
                start: date = date(2026, 1, 1)) -> list[date]:
    days = [start + timedelta(days=i) for i in range(len(closes))]
    for d, c in zip(days, closes, strict=False):
        db.add(OhlcvDaily(stock_id=stock_id, date=d, open=c, high=c + 1,
                          low=max(c - 1, 0.01), close=c, volume=1_000_000))
    return days


def _mock_fundamentals(monkeypatch):
    """Neutral fundamentals + no news for every ticker — recompute_all runs
    entirely off the mocked seam (anti-network guard stays untriggered)."""
    micro = MicroData(
        return_on_equity=0.20, profit_margins=0.15, free_cashflow=1e9,
        debt_to_equity=50.0, current_ratio=2.0,
    )
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: Fundamentals(ticker=ticker, micro=micro),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])


# ---------------------------------------------------------------------------
# 1. Qualità recompute: skip + purge
# ---------------------------------------------------------------------------

def test_recompute_all_skips_etf_and_purges_stale_score(db: Session, monkeypatch):
    _mock_fundamentals(monkeypatch)
    score_service.clear_sector_stats_cache()

    eq1 = _stock(db, "EQ1")
    eq2 = _stock(db, "EQ2")
    etf = _stock(db, "TZA", instrument_type="etf")
    for s in (eq1, eq2, etf):
        _seed_ohlcv(db, s.id, [100.0 + i * 0.1 for i in range(250)])
    # Stale nonsense row from a pre-flag recompute (the TZA 66.8 case).
    db.add(StockScore(
        stock_id=etf.id, composite=66.8, risk_tier="aggressive",
        computed_at=NOW, breakdown="{}",
    ))
    db.commit()

    ok, failed = score_service.recompute_all(db)
    assert ok == 2                    # only the two equities are scored
    assert failed == 0

    scored_ids = set(db.execute(select(StockScore.stock_id)).scalars().all())
    assert scored_ids == {eq1.id, eq2.id}   # ETF row purged, none re-added


def test_composite_percentiles_exclude_etf_after_recompute(db: Session, monkeypatch):
    """Sector/universe percentiles COUNT over stock_scores rows — once the
    recompute purges the ETF's row, the ETF drops out of both denominators
    automatically (no extra filtering needed in scores.py)."""
    _mock_fundamentals(monkeypatch)
    score_service.clear_sector_stats_cache()

    eq1 = _stock(db, "EQ1")
    eq2 = _stock(db, "EQ2")
    # Same sector as the equities: without the purge it would inflate peer_n.
    etf = _stock(db, "TQQQ", instrument_type="etf")
    for s in (eq1, eq2, etf):
        _seed_ohlcv(db, s.id, [100.0 + i * 0.1 for i in range(250)])
    db.add(StockScore(
        stock_id=etf.id, composite=99.0, risk_tier="aggressive",
        computed_at=NOW, breakdown="{}",
    ))
    db.commit()

    score_service.recompute_all(db)
    eq_score = db.execute(
        select(StockScore).where(StockScore.stock_id == eq1.id)
    ).scalars().one()
    pct = _composite_percentiles(db, "Technology", eq_score.composite)
    assert pct["peer_n"] == 2         # equities only — ETF is not a peer
    # Universe percentile is a share over 2 scored rows: 50 or 100, never a
    # value diluted by a third (ETF) row.
    assert pct["universe_percentile"] in (50, 100)


def test_recompute_endpoint_rejects_etf(db: Session):
    """The single-stock recompute escape hatch must not resurrect an ETF
    score row that recompute_all just purged."""
    user = User(username="admin", password_hash="x")
    db.add(user)
    _stock(db, "TZA", instrument_type="etf")
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        r = client.post("/api/stocks/TZA/score/recompute")
        assert r.status_code == 422
        assert "ETF" in r.json()["detail"]
        assert db.execute(select(StockScore)).scalars().first() is None
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 2. Market-neutral benchmark: companies only
# ---------------------------------------------------------------------------

def _bull_alert(db: Session, stock_id: int, sig_day: date, price: float) -> Alert:
    a = Alert(
        stock_id=stock_id, trigger_price=price, signal_date=sig_day,
        signal_name="trend_pullback",
        snapshot=json.dumps({"tone": "bull", "strength": 70, "probability": 55}),
    )
    db.add(a)
    db.flush()
    return a


def test_universe_benchmark_excludes_etf_parity(db: Session, monkeypatch):
    """Benchmark with vs without the ETF must DIFFER (the leveraged series
    distorts the mean), and mature_outcomes must store the companies-only
    value — while the ETF's own alert still gets an outcome row with its
    entry/forward math intact."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)

    eq1 = _stock(db, "EQ1")
    eq2 = _stock(db, "EQ2")
    etf = _stock(db, "TZA", instrument_type="etf")
    n = 20
    _seed_ohlcv(db, eq1.id, [100.0 + i for i in range(n)])          # ~+1%/day
    _seed_ohlcv(db, eq2.id, [50.0 + 0.5 * i for i in range(n)])     # ~+1%/day
    # 3x-leveraged-style series: +20%/day compounding — wrecks any mean.
    etf_days = _seed_ohlcv(db, etf.id, [10.0 * (1.2 ** i) for i in range(n)])
    sig_day = etf_days[10]
    a_eq = _bull_alert(db, eq1.id, sig_day, 110.0)
    a_etf = _bull_alert(db, etf.id, sig_day, 10.0 * (1.2 ** 10))
    db.commit()

    # Parity check on the loader itself.
    means_all = sos._universe_fwd_means(sos._load_universe_closes(db), 3)
    means_ex = sos._universe_fwd_means(
        sos._load_universe_closes(db, exclude_etf=True), 3
    )
    assert means_all[sig_day] != pytest.approx(means_ex[sig_day])

    added = sos.mature_outcomes(db)
    assert added == 2
    rows = {r.alert_id: r for r in db.execute(select(SignalOutcome)).scalars().all()}

    # Both rows carry the companies-only benchmark.
    assert rows[a_eq.id].universe_mean_fwd == pytest.approx(means_ex[sig_day])
    assert rows[a_etf.id].universe_mean_fwd == pytest.approx(means_ex[sig_day])

    # The ETF alert's OWN entry/forward math is untouched by the exclusion.
    etf_row = rows[a_etf.id]
    assert etf_row.entry_close == pytest.approx(10.0 * (1.2 ** 10))
    assert etf_row.forward_close == pytest.approx(10.0 * (1.2 ** 13))
    assert etf_row.abs_hit == 1
    assert etf_row.mkt_neutral_excess is not None


def test_load_universe_closes_exclude_etf_noop_without_etfs(db: Session):
    """exclude_etf=True on an all-equity universe is a no-op (same rows)."""
    eq = _stock(db, "EQ1")
    _seed_ohlcv(db, eq.id, [100.0, 101.0, 102.0])
    db.commit()
    full = sos._load_universe_closes(db)
    ex = sos._load_universe_closes(db, exclude_etf=True)
    assert set(full.keys()) == set(ex.keys()) == {eq.id}


# ---------------------------------------------------------------------------
# 3. Screener filter + payload surfacing
# ---------------------------------------------------------------------------

def test_search_exclude_etf_filter(db: Session):
    _stock(db, "AAPL")
    _stock(db, "TZA", instrument_type="etf")
    db.commit()

    both = search_stocks(db, StockFilter())
    assert sorted(i.stock.ticker for i in both.items) == ["AAPL", "TZA"]

    only_eq = search_stocks(db, StockFilter(exclude_etf=True))
    assert [i.stock.ticker for i in only_eq.items] == ["AAPL"]
    assert only_eq.total == 1


def test_search_api_surfaces_instrument_type_and_exclude_etf_param(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    _stock(db, "AAPL")
    _stock(db, "TZA", instrument_type="etf")
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        r = client.get("/api/stocks/search")
        assert r.status_code == 200
        by_ticker = {i["stock"]["ticker"]: i["stock"] for i in r.json()["items"]}
        assert by_ticker["AAPL"]["instrument_type"] == "equity"
        assert by_ticker["TZA"]["instrument_type"] == "etf"

        r = client.get("/api/stocks/search?exclude_etf=true")
        assert r.status_code == 200
        assert [i["stock"]["ticker"] for i in r.json()["items"]] == ["AAPL"]
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 4. stock_metrics as-of in the search response
# ---------------------------------------------------------------------------

def test_search_api_metrics_computed_at(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    s = _stock(db, "AAPL")
    db.add(StockMetrics(stock_id=s.id, computed_at=NOW, last_close=100.0))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        r = client.get("/api/stocks/search")
        assert r.status_code == 200
        asof = r.json()["metrics_computed_at"]
        assert asof is not None
        # UTC-tagged ISO (SQLite returns naive; the router re-tags) so the
        # FE staleness math has an explicit offset.
        parsed = datetime.fromisoformat(asof)
        assert parsed.tzinfo is not None
        assert parsed == NOW
    finally:
        app.dependency_overrides.clear()


def test_search_api_metrics_computed_at_none_without_rows(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    _stock(db, "AAPL")
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        r = client.get("/api/stocks/search")
        assert r.status_code == 200
        assert r.json()["metrics_computed_at"] is None
    finally:
        app.dependency_overrides.clear()
