"""L2 quote snapshots + the batch deadline / warm-fallback ladder.

Both exist because of the 2026-07-23 incident: under Yahoo rate-limiting,
live-quote requests took 43-50 SECONDS, saturated the sync threadpool and got
the pod liveness-killed. An unbounded wait is not a slow response — it is an
outage. These tests pin the two properties that prevent a repeat: a request
never blocks indefinitely, and there is always something to serve.
"""
import importlib
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


# ─── Single-flight ──────────────────────────────────────────────────────────
# N concurrent callers missing the 10s TTL for the SAME symbol used to start N
# upstream requests each. The dashboard polls several cards, the batch path
# fans out 8 workers, and a cold cache after a restart makes them all miss at
# once — duplicate load that is also what pushes Yahoo into the 429s that open
# the quotes breaker.

def test_concurrent_callers_share_one_upstream_fetch() -> None:
    """THE point of single-flight: ten callers, one fetch."""
    import threading

    calls = []
    barrier = threading.Barrier(10)

    def slow_fetch(t, **_k):
        calls.append(t)
        time.sleep(0.25)          # long enough for the others to pile up
        return LiveQuote(ticker=t, price=42.0, market_state="OPEN",
                         fetched_at=time.time())

    live_quote_service._fetch_fresh = slow_fetch  # type: ignore[assignment]
    try:
        results = []

        def worker():
            barrier.wait()        # all ten arrive together
            results.append(live_quote_service.get_quote("AAPL"))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(calls) == 1, f"{len(calls)} upstream fetches for one ticker"
        assert len(results) == 10
        assert all(r.price == 42.0 for r in results), "followers got the leader's quote"
    finally:
        importlib.reload(live_quote_service)


def test_a_failing_leader_does_not_wedge_the_followers() -> None:
    """If the leader raises, its in-flight slot must still be released —
    otherwise one exception blocks every later caller for that ticker until
    the wait times out."""
    def boom(_t, **_k):
        raise RuntimeError("upstream exploded")

    live_quote_service._fetch_fresh = boom  # type: ignore[assignment]
    try:
        try:
            live_quote_service.get_quote("AAPL")
        except RuntimeError:
            pass
        assert "AAPL" not in live_quote_service._INFLIGHT, "slot leaked"
    finally:
        importlib.reload(live_quote_service)


def test_different_tickers_are_not_serialised() -> None:
    """Single-flight is PER TICKER. Coalescing across symbols would turn the
    batch path back into a serial loop, which is the thing the thread pool
    exists to avoid."""
    import threading

    started = threading.Semaphore(0)
    release = threading.Event()

    def blocking_fetch(t, **_k):
        started.release()
        release.wait(timeout=5)
        return LiveQuote(ticker=t, price=1.0, market_state="OPEN", fetched_at=time.time())

    live_quote_service._fetch_fresh = blocking_fetch  # type: ignore[assignment]
    try:
        for tk in ("AAPL", "MSFT"):
            threading.Thread(target=live_quote_service.get_quote, args=(tk,)).start()
        # Both must get INTO the fetch; if they were serialised only one would.
        assert started.acquire(timeout=3)
        assert started.acquire(timeout=3), "the second ticker was blocked by the first"
    finally:
        release.set()
        time.sleep(0.1)
        importlib.reload(live_quote_service)
