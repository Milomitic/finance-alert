"""Lane ESP-1 — Esplora (/sectors) data-quality cleanup (audit 2026-07-08).

Five behaviors under test:

1. ETF exclusion on every /api/sectors surface: rollup medians, industry
   rollup, detail peers, overview total. Parity style — the same seed
   with the ETF flipped to equity produces DIFFERENT medians, proving
   the filter is what keeps SPY/TQQQ P/Es out of the Financials bench.
2. ETF exclusion inside `_build_sector_stats` (the fundamentals-by-
   sector grouping feeding sector_stats_service.compute) — the medians
   that benchmark the Value pillar.
3. N+1 fix: get_sector_detail loads all StockScore rows in ONE SELECT.
4. Cache wiring: recompute_all clears the /sectors overview cache.
5. backfill_null_sectors script: NULL-only, GICS-normalized, dry-run,
   ETF skip — on a fixture fetcher (anti-network guard stays happy).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, StockScore, User
from app.services import (
    score_service,
    sectors_overview_cache,
    stock_fundamentals_service,
    stock_news_service,
)
from app.services.stock_fundamentals_service import Fundamentals, MicroData

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures / seeding helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_process_caches():
    """Snapshot + restore the process-global caches this module pokes:
    the fundamentals L1 (we seed fake PEs into it) and the overview TTL
    cache (60s TTL would leak a payload into the next test)."""
    saved_l1 = dict(stock_fundamentals_service._CACHE)  # noqa: SLF001
    sectors_overview_cache.clear_overview_cache()
    score_service.clear_sector_stats_cache()
    yield
    stock_fundamentals_service._CACHE.clear()  # noqa: SLF001
    stock_fundamentals_service._CACHE.update(saved_l1)  # noqa: SLF001
    sectors_overview_cache.clear_overview_cache()
    score_service.clear_sector_stats_cache()


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


def _seed_l1_pe(ticker: str, pe: float) -> None:
    """Plant a warm L1 fundamentals entry — the rollup medians read the
    in-memory cache only (no network, no DB)."""
    stock_fundamentals_service._CACHE[ticker] = Fundamentals(  # noqa: SLF001
        ticker=ticker, micro=MicroData(trailing_pe=pe),
    )


# ---------------------------------------------------------------------------
# 1. ETF exclusion on the /api/sectors surfaces
# ---------------------------------------------------------------------------

def test_sector_rollup_median_parity_with_without_etf(client: TestClient, db: Session):
    """With the ETF flagged, the Financials P/E median is computed on
    equities only; re-flagging the same row as equity CHANGES the median
    — the exclusion (not median robustness) keeps the number honest."""
    _stock(db, "JPM")
    _stock(db, "BAC")
    etf = _stock(db, "SPY", instrument_type="etf", composite=None)
    db.commit()
    _seed_l1_pe("JPM", 10.0)
    _seed_l1_pe("BAC", 20.0)
    _seed_l1_pe("SPY", 1000.0)  # nonsense ETF P/E — must never enter

    body = client.get("/api/sectors").json()
    fin = next(s for s in body if s["name"] == "Financials")
    assert fin["stock_count"] == 2               # ETF not a member
    assert fin["median_pe"] == pytest.approx(15.0)  # median(10, 20)

    # Parity: same data, ETF flipped to equity → median moves to 20.
    etf.instrument_type = "equity"
    db.commit()
    body2 = client.get("/api/sectors").json()
    fin2 = next(s for s in body2 if s["name"] == "Financials")
    assert fin2["stock_count"] == 3
    assert fin2["median_pe"] == pytest.approx(20.0)
    assert fin2["median_pe"] != fin["median_pe"]


def test_sector_detail_excludes_etf_from_peers_and_medians(client: TestClient, db: Session):
    _stock(db, "JPM")
    _stock(db, "BAC")
    _stock(db, "TQQQ", instrument_type="etf", composite=None)
    db.commit()
    _seed_l1_pe("JPM", 10.0)
    _seed_l1_pe("BAC", 20.0)
    _seed_l1_pe("TQQQ", 500.0)

    body = client.get("/api/sectors/Financials/detail").json()
    tickers = {r["ticker"] for r in body["stocks"]}
    assert "TQQQ" not in tickers
    assert tickers == {"JPM", "BAC"}
    assert body["kpis"]["stock_count"] == 2
    assert body["kpis"]["median_pe"] == pytest.approx(15.0)
    assert all(r["ticker"] != "TQQQ" for r in body["top_picks"])


def test_sector_detail_all_etf_sector_is_404(client: TestClient, db: Session):
    """A sector label carried ONLY by ETFs has no equity peers → 404,
    not an empty page."""
    _stock(db, "TZA", sector="Leveraged", instrument_type="etf", composite=None)
    db.commit()
    assert client.get("/api/sectors/Leveraged/detail").status_code == 404


def test_overview_counts_and_industries_exclude_etf(client: TestClient, db: Session):
    _stock(db, "JPM")
    _stock(db, "BAC")
    _stock(db, "SPY", instrument_type="etf", composite=None)
    db.commit()

    body = client.get("/api/sectors/overview").json()
    assert body["total_stocks"] == 2             # equities only
    banks = next(i for i in body["industries"] if i["name"] == "Banks")
    assert banks["stock_count"] == 2             # ETF's industry row not inflated


def test_overview_cache_serves_memoized_payload(client: TestClient, db: Session):
    """Second hit within TTL returns the memoized payload (no recompute):
    a stock added between the two hits doesn't show until invalidation."""
    _stock(db, "JPM")
    db.commit()
    first = client.get("/api/sectors/overview").json()
    assert first["total_stocks"] == 1

    _stock(db, "BAC")
    db.commit()
    assert client.get("/api/sectors/overview").json()["total_stocks"] == 1  # cached

    sectors_overview_cache.clear_overview_cache()
    assert client.get("/api/sectors/overview").json()["total_stocks"] == 2  # fresh


# ---------------------------------------------------------------------------
# 2. ETF exclusion inside _build_sector_stats (Value-pillar benchmark)
# ---------------------------------------------------------------------------

def test_build_sector_stats_excludes_etf_fundamentals(db: Session, monkeypatch):
    """The grouping that feeds sector_stats_service.compute must drop
    non-equity rows even when the CALLER forgot to pre-filter — the
    SPY-in-Financials-medians audit finding."""
    pes = {"JPM": 10.0, "BAC": 20.0, "C": 30.0, "GS": 40.0, "SPY": 1000.0}
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda t, force_refresh=False: Fundamentals(
            ticker=t, micro=MicroData(trailing_pe=pes[t]),
        ),
    )
    for t in ("JPM", "BAC", "C", "GS"):
        _stock(db, t, composite=None)
    spy = _stock(db, "SPY", instrument_type="etf", composite=None)
    db.commit()
    stocks = list(db.execute(select(Stock)).scalars().all())

    bundle = score_service._build_sector_stats(stocks, use_cache=False)
    fin = bundle.by_sector["Financials"]
    assert fin.n == 4                              # SPY not a member
    assert fin.pe_median == pytest.approx(25.0)    # median(10,20,30,40)

    # Parity: flip SPY to equity → median shifts to 30 (10,20,30,40,1000).
    spy.instrument_type = "equity"
    db.commit()
    stocks2 = list(db.execute(select(Stock)).scalars().all())
    bundle2 = score_service._build_sector_stats(stocks2, use_cache=False)
    assert bundle2.by_sector["Financials"].n == 5
    assert bundle2.by_sector["Financials"].pe_median == pytest.approx(30.0)
    assert bundle2.by_sector["Financials"].pe_median != fin.pe_median


# ---------------------------------------------------------------------------
# 3. N+1 fix: one StockScore SELECT for the whole detail page
# ---------------------------------------------------------------------------

def test_sector_detail_loads_scores_in_single_query(client: TestClient, db: Session):
    for i in range(10):
        _stock(db, f"FIN{i}", composite=50.0 + i)
    db.commit()

    counted = {"stock_scores_selects": 0}

    def _count(_conn, _cursor, statement, *_args):
        if "FROM stock_scores" in statement:
            counted["stock_scores_selects"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _count)
    try:
        resp = client.get("/api/sectors/Financials/detail")
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert resp.status_code == 200
    assert resp.json()["kpis"]["stock_count"] == 10
    # The old loop issued 10 SELECTs (one per stock); now exactly one IN query.
    assert counted["stock_scores_selects"] == 1


# ---------------------------------------------------------------------------
# 4. Cache wiring: recompute_all invalidates the overview payload
# ---------------------------------------------------------------------------

def _seed_ohlcv(db: Session, stock_id: int, n: int = 250) -> None:
    start = date(2025, 10, 1)
    for i in range(n):
        c = 100.0 + i * 0.1
        db.add(OhlcvDaily(stock_id=stock_id, date=start + timedelta(days=i),
                          open=c, high=c + 1, low=c - 1, close=c,
                          volume=1_000_000))


def test_recompute_all_clears_overview_cache(db: Session, monkeypatch):
    micro = MicroData(return_on_equity=0.20, profit_margins=0.15,
                      free_cashflow=1e9, debt_to_equity=50.0, current_ratio=2.0)
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda t, force_refresh=False: Fundamentals(ticker=t, micro=micro),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda t, limit=5: [])

    eq = _stock(db, "EQ1", composite=None)
    _seed_ohlcv(db, eq.id)
    db.commit()

    sectors_overview_cache.store({"stale": "payload"})
    assert sectors_overview_cache.get_cached() is not None

    ok, failed = score_service.recompute_all(db)
    assert ok == 1 and failed == 0
    # The post-recompute hook dropped the memoized payload — the next
    # /sectors hit recomputes with the fresh composites.
    assert sectors_overview_cache.get_cached() is None


# ---------------------------------------------------------------------------
# 5. backfill_null_sectors script (fixture fetcher, no network)
# ---------------------------------------------------------------------------

def test_backfill_fills_null_sectors_normalized(db: Session):
    from app.scripts.backfill_null_sectors import backfill_null_sectors

    a = _stock(db, "AAA", sector=None, industry=None, composite=None)
    b = _stock(db, "BBB", sector=None, industry=None, composite=None)
    keep = _stock(db, "KEEP", sector="Financials", composite=None)  # non-NULL: untouched
    db.commit()

    infos = {
        "AAA": {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
        "BBB": {"sector": "Healthcare", "industry": "Biotechnology"},
    }
    summary = backfill_null_sectors(db, lambda t: infos.get(t))

    db.refresh(a); db.refresh(b); db.refresh(keep)
    # yfinance labels land NORMALIZED, never raw.
    assert a.sector == "Consumer Discretionary"
    assert b.sector == "Health Care"
    assert a.industry is not None      # canonical_industry output, non-raw
    assert keep.sector == "Financials"
    assert summary.examined == 2
    assert summary.updated == 2


def test_backfill_dry_run_writes_nothing(db: Session):
    from app.scripts.backfill_null_sectors import backfill_null_sectors

    a = _stock(db, "AAA", sector=None, composite=None)
    db.commit()

    summary = backfill_null_sectors(
        db, lambda t: {"sector": "Technology"}, dry_run=True,
    )
    db.refresh(a)
    assert a.sector is None                       # nothing persisted
    assert summary.updated == 1                   # ...but the report shows it
    assert summary.changes == [("AAA", "Information Technology", None)]


def test_backfill_skips_etfs_and_counts_failures(db: Session):
    from app.scripts.backfill_null_sectors import backfill_null_sectors

    _stock(db, "TZA", sector=None, instrument_type="etf", composite=None)
    _stock(db, "DEAD", sector=None, composite=None)   # fetcher returns None
    _stock(db, "EMPTY", sector=None, composite=None)  # payload has no sector
    db.commit()

    fetched: list[str] = []

    def fetcher(t: str) -> dict | None:
        fetched.append(t)
        return None if t == "DEAD" else {}

    summary = backfill_null_sectors(db, fetcher)
    assert "TZA" not in fetched                   # ETF never hits the network
    assert summary.skipped_etf == 1
    assert summary.fetch_failed == 1
    assert summary.no_data == 1
    assert summary.updated == 0
