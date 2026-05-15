"""Tests for the L2 persistence layer of fundamentals + news caches."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models import FetchCache
from app.services import fetch_cache_store
from app.services.stock_fundamentals_service import (
    AnalystAction,
    AnalystPriceTarget,
    Fundamentals,
    MicroData,
)


def test_write_then_read_roundtrips_fundamentals(db: Session):
    """The reconstructor must rebuild nested dataclasses (MicroData,
    AnalystPriceTarget, AnalystAction[]) — not just leave them as dicts."""
    f = Fundamentals(
        ticker="AAPL",
        next_earnings_date="2026-08-07",
        next_eps_estimate=1.43,
        next_revenue_estimate=90_000_000_000.0,
        micro=MicroData(trailing_pe=27.5, return_on_equity=1.41),
        price_target=AnalystPriceTarget(
            current=210.0, low=180.0, mean=240.0, median=235.0, high=300.0,
        ),
        analyst_actions=[
            AnalystAction(
                date="2026-05-01", firm="UBS", to_grade="Neutral",
                from_grade="Neutral", action="main",
                current_price_target=296.0, prior_price_target=287.0,
                price_target_action="Raises",
            ),
        ],
    )
    fetch_cache_store.write_fundamentals(db, f)

    out = fetch_cache_store.read_fundamentals(db, "AAPL", max_age_seconds=3600)
    assert out is not None
    assert out.ticker == "AAPL"
    assert out.next_earnings_date == "2026-08-07"
    # Nested dataclass: must be reconstructed, not a dict
    assert isinstance(out.micro, MicroData)
    assert out.micro.trailing_pe == 27.5
    assert isinstance(out.price_target, AnalystPriceTarget)
    assert out.price_target.mean == 240.0
    assert len(out.analyst_actions) == 1
    assert isinstance(out.analyst_actions[0], AnalystAction)
    assert out.analyst_actions[0].current_price_target == 296.0


def test_read_returns_none_when_stale(db: Session):
    """TTL check happens at read time — past-TTL rows are skipped, leaving
    the network refetch path to run instead."""
    f = Fundamentals(ticker="AAPL", next_earnings_date="2026-08-07")
    fetch_cache_store.write_fundamentals(db, f)

    # Backdate the row to 25h ago (past the 24h TTL)
    row = db.query(FetchCache).filter_by(ticker="AAPL", kind="fundamentals").one()
    row.fetched_at = datetime.now(UTC) - timedelta(hours=25)
    db.commit()

    assert fetch_cache_store.read_fundamentals(db, "AAPL", 24 * 3600) is None


def test_write_is_upsert_not_insert(db: Session):
    """Writing the same ticker twice must update the existing row, not
    raise IntegrityError on the composite (ticker, kind) PK."""
    # Both payloads carry at least one populated micro field so the new
    # `_is_payload_too_partial` gate doesn't classify them as stale on
    # read. The test's purpose is the UPSERT semantic, not data quality.
    f1 = Fundamentals(ticker="AAPL", next_earnings_date="2026-05-01",
                      micro=MicroData(trailing_pe=27.5))
    fetch_cache_store.write_fundamentals(db, f1)

    f2 = Fundamentals(ticker="AAPL", next_earnings_date="2026-08-07",
                      micro=MicroData(trailing_pe=28.0))
    fetch_cache_store.write_fundamentals(db, f2)

    rows = db.query(FetchCache).filter_by(ticker="AAPL").all()
    assert len(rows) == 1  # UPSERT, not duplicate
    out = fetch_cache_store.read_fundamentals(db, "AAPL", max_age_seconds=3600)
    assert out is not None
    assert out.next_earnings_date == "2026-08-07"  # value updated


def test_news_roundtrips(db: Session):
    items = [
        {"title": "Apple Q3", "link": "https://x.com/1", "publisher": "WSJ", "published_at": "2026-05-01T10:00:00Z"},
        {"title": "Apple Q4", "link": "https://x.com/2", "publisher": "Reuters", "published_at": "2026-05-02T10:00:00Z"},
    ]
    fetch_cache_store.write_news(db, "AAPL", items)
    out = fetch_cache_store.read_news(db, "AAPL", max_age_seconds=3600)
    assert out is not None
    assert len(out) == 2
    assert out[0]["title"] == "Apple Q3"


def test_hydrate_skips_stale_rows(db: Session):
    """Hydration filters out past-TTL rows — a stale row in L2 must NOT
    pollute L1 after a restart."""
    # Both payloads carry a non-empty micro so the new
    # `_is_payload_too_partial` gate doesn't classify them stale-on-read.
    # Tested separately in test_stock_detail_partial_fetch_and_eod_regression.
    fetch_cache_store.write_fundamentals(
        db, Fundamentals(ticker="FRESH", micro=MicroData(trailing_pe=20.0))
    )
    fetch_cache_store.write_fundamentals(
        db, Fundamentals(ticker="STALE", micro=MicroData(trailing_pe=18.0))
    )

    # Backdate STALE's row past TTL
    row = db.query(FetchCache).filter_by(ticker="STALE", kind="fundamentals").one()
    row.fetched_at = datetime.now(UTC) - timedelta(hours=48)
    db.commit()

    out, skipped = fetch_cache_store.hydrate_all_fundamentals(db, max_age_seconds=24 * 3600)
    assert "FRESH" in out
    assert "STALE" not in out


def test_get_fundamentals_uses_l2_after_l1_clear(db: Session, monkeypatch):
    """End-to-end of the stack: a write goes through both layers; clearing
    L1 (simulating restart) and reading again should serve from L2 without
    hitting the network."""
    from app.core.db import SessionLocal
    from app.services import stock_fundamentals_service as svc

    # Stub the upstream fetch so we can detect any call to it.
    # The stub returns a non-partial payload (one populated micro field)
    # so the new `_is_payload_too_partial` gate doesn't reject it on
    # read and force a re-fetch — that gate is exercised separately in
    # test_stock_detail_partial_fetch_and_eod_regression.
    upstream_calls = []
    def stub_fetch(ticker: str) -> Fundamentals:
        upstream_calls.append(ticker)
        return Fundamentals(
            ticker=ticker,
            next_earnings_date="2026-08-07",
            micro=MicroData(trailing_pe=27.5),
        )
    monkeypatch.setattr(svc, "_fetch_fresh", stub_fetch)

    # Make get_fundamentals open sessions against the test DB. The simplest
    # path: monkeypatch SessionLocal in the service path to return the test
    # session via a context manager that doesn't close.
    class _FakeCtx:
        def __init__(self, sess): self.sess = sess
        def __enter__(self): return self.sess
        def __exit__(self, *a): pass
    monkeypatch.setattr(
        "app.core.db.SessionLocal",
        lambda: _FakeCtx(db),
    )

    # Start clean. clear_cache() now wipes BOTH layers, which is what we
    # want for the FIRST half of this test (forces an upstream call).
    svc.clear_cache()
    # First call: both layers miss → upstream fetched, L1 + L2 written
    f1 = svc.get_fundamentals("AAPL")
    assert f1.next_earnings_date == "2026-08-07"
    assert upstream_calls == ["AAPL"]

    # Simulate a process RESTART (not a full cache wipe): L1 dict goes
    # away because we lost the process, but L2 rows in fetch_cache survive.
    # Poke the in-memory dict directly so we don't accidentally also nuke L2.
    svc._CACHE.clear()
    upstream_calls.clear()

    # Second call: L1 miss, L2 hit → no upstream call
    f2 = svc.get_fundamentals("AAPL")
    assert f2.next_earnings_date == "2026-08-07"
    assert upstream_calls == []  # NETWORK NOT HIT — proves L2 served the request
