"""L2 quote snapshots + the batch deadline / warm-fallback ladder.

Both exist because of the 2026-07-23 incident: under Yahoo rate-limiting,
live-quote requests took 43-50 SECONDS, saturated the sync threadpool and got
the pod liveness-killed. An unbounded wait is not a slow response — it is an
outage. These tests pin the two properties that prevent a repeat: a request
never blocks indefinitely, and there is always something to serve.
"""
import time

import pytest

from app.services import live_quote_l2, live_quote_service, yfinance_health
from app.services.live_quote_service import LiveQuote


def setup_function() -> None:
    live_quote_service.clear_cache()
    live_quote_l2.reset()
    yfinance_health.reset()


def test_l2_roundtrip_persists_and_reloads(db) -> None:
    """mark_dirty → flush → load_all survives the process boundary."""
    q = LiveQuote(
        ticker="AAPL", price=200.0, prev_close=190.0, currency="USD",
        market_state="OPEN", fetched_at=time.time(), as_of_date="2026-07-23",
    )
    live_quote_l2.mark_dirty("AAPL", live_quote_service._quote_to_l2_payload(q))
    assert live_quote_l2.pending() == 1

    assert live_quote_l2.flush(db) == 1
    assert live_quote_l2.pending() == 0        # drained

    loaded = live_quote_l2.load_all(db)
    assert loaded["AAPL"]["price"] == 200.0
    assert loaded["AAPL"]["prev_close"] == 190.0


def test_l2_flush_is_idempotent_upsert(db) -> None:
    """Re-flushing the same ticker updates the row, never duplicates it."""
    for price in (100.0, 111.0):
        live_quote_l2.mark_dirty("MSFT", {"price": price, "prev_close": 99.0})
        live_quote_l2.flush(db)
    loaded = live_quote_l2.load_all(db)
    assert loaded["MSFT"]["price"] == 111.0    # last write wins, single row


def test_restored_snapshot_is_flagged_stale_not_open() -> None:
    """A restored price must NEVER claim to be live — that is the only way
    this cache could actually mislead someone."""
    q = live_quote_service._quote_from_l2_payload(
        "AAPL", {"price": 210.0, "prev_close": 200.0, "fetched_at": 1.0}
    )
    assert q.market_state == "STALE"
    assert q.price == 210.0
    assert q.change_abs == pytest.approx(10.0)
    assert q.change_pct == pytest.approx(5.0)


def test_open_breaker_serves_warm_without_fanning_out(monkeypatch) -> None:
    """With the quotes lane open we must not spin up workers just to have each
    one bail — and we must still return a usable price."""
    live_quote_service._LAST_LIVE["AAPL"] = LiveQuote(
        ticker="AAPL", price=123.0, market_state="OPEN", fetched_at=time.time()
    )
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("429", lane=yfinance_health.LANE_QUOTES)

    def boom(*_a, **_k):
        raise AssertionError("no fetch may be attempted while the breaker is open")
    monkeypatch.setattr(live_quote_service, "get_quote", boom)

    out = live_quote_service.get_quotes_batch(["AAPL"])
    assert out["AAPL"].price == 123.0


def test_batch_deadline_serves_warm_instead_of_blocking(monkeypatch) -> None:
    """THE regression test for the 50-second request. A straggler must not
    hold the batch: past the deadline we serve what we have."""
    live_quote_service._LAST_LIVE["SLOW"] = LiveQuote(
        ticker="SLOW", price=50.0, market_state="OPEN", fetched_at=time.time()
    )

    def slow(_t, **_k):
        time.sleep(1.5)
        return LiveQuote(ticker="SLOW", price=999.0, market_state="OPEN")
    monkeypatch.setattr(live_quote_service, "get_quote", slow)

    t0 = time.perf_counter()
    out = live_quote_service.get_quotes_batch(["SLOW"], deadline_seconds=0.05)
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.0                 # did NOT wait for the slow fetch
    assert out["SLOW"].price == 50.0     # served the last good quote instead


def test_warm_ladder_falls_through_to_l2_snapshot() -> None:
    """With no live cache at all — the state right after a restart — the
    persisted snapshot is what makes the first page load instant."""
    live_quote_service._L2_SNAPSHOT["NVDA"] = {"price": 777.0, "prev_close": 700.0}
    q = live_quote_service._warm_or_eod("NVDA")
    assert q.price == 777.0
    assert q.market_state == "STALE"
