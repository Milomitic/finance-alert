"""Cron/boot scan fetch plan: per-stock incremental/backfill split.

The old cron path decided per CHUNK: if any stock in a 100-stock chunk was
stale, the WHOLE chunk was re-downloaded at period="10y" (~2520 bars × ~99
fresh stocks wasted, every boot catch-up). Ported the manual path's per-stock
split: fresh stocks fetch incrementally from start=min(latest)+1, only truly
stale/empty stocks pay the 10y backfill, and an all-up-to-date population
skips yfinance entirely.
"""
from datetime import date, timedelta

import app.core.db as db_module
from app.models import OhlcvDaily, Stock
from app.scheduler.jobs import scan_alerts as job

TODAY = date.today()


def _stock(db, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def _bar(db, stock_id: int, d: date) -> None:
    db.add(OhlcvDaily(stock_id=stock_id, date=d, open=1, high=1, low=1, close=1, volume=1))


def _run(monkeypatch, db):
    """Run the job against the test DB, capturing fetch_and_upsert calls."""
    monkeypatch.setattr(job, "SessionLocal", db_module.SessionLocal)
    calls: list[tuple[list[str], str | None, date | None]] = []

    def fake_fetch(session, stocks, *, period=None, start=None):
        calls.append((sorted(s.ticker for s in stocks), period, start))

    monkeypatch.setattr(job, "fetch_and_upsert", fake_fetch)
    tracked: list[str] = []
    monkeypatch.setattr(
        job, "run_tracked_scan",
        lambda session, trigger, existing_run=None: tracked.append(trigger),
    )
    job.run_scan_alerts(trigger="cron")
    return calls, tracked


def test_fetch_plan_splits_per_stock(db, monkeypatch):
    fresh = _stock(db, "FRESH")     # latest 2 days ago -> incremental
    stale = _stock(db, "STALE")     # latest 60 days ago -> backfill
    _stock(db, "EMPTY")             # no bars -> backfill
    _bar(db, fresh.id, TODAY - timedelta(days=2))
    _bar(db, stale.id, TODAY - timedelta(days=60))
    db.commit()

    calls, tracked = _run(monkeypatch, db)

    inc = [c for c in calls if c[2] is not None]      # start= calls
    back = [c for c in calls if c[1] == "10y"]        # period= calls
    assert len(inc) == 1
    assert inc[0][0] == ["FRESH"]
    assert inc[0][2] == TODAY - timedelta(days=1)     # min(latest)+1
    assert len(back) == 1
    assert back[0][0] == ["EMPTY", "STALE"]           # only truly stale/empty
    assert tracked == ["cron"]                        # evaluate still runs


def test_fetch_plan_skips_when_all_up_to_date(db, monkeypatch):
    a = _stock(db, "AAA")
    _bar(db, a.id, TODAY)                             # already has today's bar
    db.commit()

    calls, tracked = _run(monkeypatch, db)

    assert calls == []                                # no yfinance call at all
    assert tracked == ["cron"]                        # evaluate still runs
