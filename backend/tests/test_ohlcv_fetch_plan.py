"""Shared OHLCV fetch planner (ohlcv_fetch_plan) — the seam both scan paths
(manual endpoint + cron job) consume.

Invariants under test, plan-level (the two callers' integration behavior is
covered by test_scan_alerts_fetch_plan / test_ohlcv_split_and_quarantine):

- per-stock incremental/backfill split on the 30-day cutoff;
- staleness sort (oldest latest-bar first) so chunk windows stay tight;
- quarantine ONLY for zero-bar stocks (a stale stock WITH data is never
  quarantined, whatever its nodata streak says);
- overlap-by-one-session: incremental chunks start AT min(latest), not +1;
- smart-skip: an all-up-to-date chunk is yielded as KIND_SKIP (no fetch).
"""
from datetime import date, timedelta

from app.models import OhlcvDaily, Stock
from app.services.ohlcv_fetch_plan import (
    KIND_BACKFILL,
    KIND_INCREMENTAL,
    KIND_SKIP,
    build_fetch_plan,
    iter_fetch_chunks,
)

TODAY = date.today()


def _stock(db, ticker: str, **kw) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US", **kw)
    db.add(s)
    db.flush()
    return s


def _bar(db, stock_id: int, d: date) -> None:
    db.add(OhlcvDaily(stock_id=stock_id, date=d, open=1, high=1, low=1, close=1, volume=1))


def test_build_fetch_plan_split_sort_and_quarantine(db):
    fresh_new = _stock(db, "FR2")     # latest 2d ago  -> incremental
    fresh_old = _stock(db, "FR9")     # latest 9d ago  -> incremental (staler)
    stale = _stock(db, "STALE")       # latest 60d ago -> backfill
    _stock(db, "EMPTY")       # no bars        -> backfill
    # Zero-bar dead ticker in quarantine window -> excluded from backfill.
    _stock(db, "DEADQ", ohlcv_nodata_streak=5, ohlcv_last_nodata_at=TODAY)
    # Stale stock WITH data and a high nodata streak: quarantine must NOT
    # touch it — only zero-bar stocks are ever quarantined by the plan.
    stale_streaky = _stock(
        db, "STRK", ohlcv_nodata_streak=9, ohlcv_last_nodata_at=TODAY
    )
    _bar(db, fresh_new.id, TODAY - timedelta(days=2))
    _bar(db, fresh_old.id, TODAY - timedelta(days=9))
    _bar(db, stale.id, TODAY - timedelta(days=60))
    _bar(db, stale_streaky.id, TODAY - timedelta(days=90))
    db.commit()

    plan = build_fetch_plan(db, list(db.query(Stock).all()))

    # Per-stock split + staleness sort (oldest latest-bar first).
    assert [s.ticker for s in plan.incremental] == ["FR9", "FR2"]
    # Backfill: no-data first (date.min), then oldest stored bar.
    assert [s.ticker for s in plan.backfill] == ["EMPTY", "STRK", "STALE"]
    # Quarantine only for the ZERO-BAR dead ticker; STRK (has data) stays in.
    assert [s.ticker for s in plan.quarantined] == ["DEADQ"]
    assert plan.total == 5
    assert plan.latest_dates[fresh_new.id] == TODAY - timedelta(days=2)


def test_iter_fetch_chunks_overlap_start_and_kinds(db):
    a = _stock(db, "A5")              # latest 5d ago
    b = _stock(db, "B3")              # latest 3d ago
    c = _stock(db, "CEMPTY")          # no bars -> backfill
    _bar(db, a.id, TODAY - timedelta(days=5))
    _bar(db, b.id, TODAY - timedelta(days=3))
    db.commit()

    plan = build_fetch_plan(db, [a, b, c])
    chunks = list(iter_fetch_chunks(plan, chunk_size=10))

    assert len(chunks) == 2
    inc_chunk, inc_kind, inc_start, inc_period = chunks[0]
    # Overlap by one session: start AT the oldest stored bar of the chunk
    # (min(latest)), NOT +1 — the newest stored bar gets re-requested.
    assert inc_kind == KIND_INCREMENTAL
    assert sorted(s.ticker for s in inc_chunk) == ["A5", "B3"]
    assert inc_start == TODAY - timedelta(days=5)
    assert inc_period is None
    back_chunk, back_kind, back_start, back_period = chunks[1]
    assert back_kind == KIND_BACKFILL
    assert [s.ticker for s in back_chunk] == ["CEMPTY"]
    assert back_start is None and back_period == "10y"


def test_iter_fetch_chunks_smart_skip_and_chunking(db):
    # Two up-to-date stocks (today's bar) + one 1-day-stale, chunk_size=2:
    # the staleness sort puts the stale one first, so chunk #1 = [stale,
    # up-to-date] fetches from min(latest) and chunk #2 = [up-to-date] is
    # smart-skipped (start >= today -> nothing new, nothing to revalidate).
    s1 = _stock(db, "UPD1")
    s2 = _stock(db, "UPD2")
    s3 = _stock(db, "LAG1")
    _bar(db, s1.id, TODAY)
    _bar(db, s2.id, TODAY)
    _bar(db, s3.id, TODAY - timedelta(days=1))
    db.commit()

    plan = build_fetch_plan(db, [s1, s2, s3])
    chunks = list(iter_fetch_chunks(plan, chunk_size=2))

    # Stable sort: LAG1 (staler) first, then UPD1/UPD2 in input order.
    assert [(k, [s.ticker for s in c]) for c, k, _st, _p in chunks] == [
        (KIND_INCREMENTAL, ["LAG1", "UPD1"]),
        (KIND_SKIP, ["UPD2"]),
    ]
    # The mixed chunk starts at the stale member's latest bar (overlap).
    assert chunks[0][2] == TODAY - timedelta(days=1)
    # The skip chunk carries no fetch parameters.
    assert chunks[1][2] is None and chunks[1][3] is None


# ─── Long-dead quarantine (found 2026-07-30) ───────────────────────────────

def test_a_symbol_with_bars_but_a_long_dead_streak_is_finally_quarantined(db):
    """The original rule never quarantined a stock that had bars, so a few
    transient misses could not knock a live symbol out. Right, but unbounded:
    APLS, CTRA, BK and TERN were found with streaks of 81-107, retried every
    scan for over three months."""
    from app.models import OhlcvDaily, Stock
    from app.services.ohlcv_fetch_plan import LONG_DEAD_STREAK, build_fetch_plan

    s = Stock(ticker="DEAD", exchange="NASDAQ", name="Dead Co", country="US",
              ohlcv_nodata_streak=LONG_DEAD_STREAK + 5,
              ohlcv_last_nodata_at=date.today())
    db.add(s)
    db.flush()
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 1, 2), open=1, high=1,
                      low=1, close=1, volume=1))       # stale but present
    db.flush()

    plan = build_fetch_plan(db, [s])
    assert [q.ticker for q in plan.quarantined] == ["DEAD"]


def test_a_live_symbol_with_a_short_streak_is_still_fetched(db):
    """A bad week upstream must not set a live symbol aside — that is the
    protection the original rule was written for and it has to survive."""
    from app.models import OhlcvDaily, Stock
    from app.services.ohlcv_fetch_plan import build_fetch_plan

    s = Stock(ticker="ALIVE", exchange="NASDAQ", name="Alive Co", country="US",
              ohlcv_nodata_streak=5, ohlcv_last_nodata_at=date.today())
    db.add(s)
    db.flush()
    db.add(OhlcvDaily(stock_id=s.id, date=date.today(), open=1, high=1,
                      low=1, close=1, volume=1))
    db.flush()

    plan = build_fetch_plan(db, [s])
    assert plan.quarantined == []
