"""Split detection (price-basis rebase) + dead-ticker quarantine.

Split: Yahoo back-adjusts RAW prices for splits, so after a split the
overlap-by-one-session bar re-downloaded for a date we already hold differs
from the stored close by ~the split ratio. The ingest must NOT splice the two
scales — it wipes and re-downloads the stock's full history on the new basis.

Quarantine: a symbol whose fetches keep returning NO data (delisted/renamed)
stops being re-attempted after QUARANTINE_STREAK empty fetches, with a weekly
re-probe. Only stocks with zero stored bars are ever quarantined by the scan
paths.
"""
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import ohlcv_service


def _seed_stock(db: Session, ticker: str = "SPLT") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.commit()
    return s


def _store_bars(db: Session, stock_id: int, start: date, closes: list[float]) -> None:
    for i, c in enumerate(closes):
        db.add(OhlcvDaily(
            stock_id=stock_id, date=start + timedelta(days=i),
            open=c, high=c + 1, low=c - 1, close=c, volume=1_000,
        ))
    db.commit()


def _frame(start: date, closes: list[float]) -> pd.DataFrame:
    idx = pd.to_datetime([start + timedelta(days=i) for i in range(len(closes))])
    return pd.DataFrame(
        {
            "Open": closes, "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes], "Close": closes,
            "Volume": [1_000] * len(closes),
        },
        index=idx,
    )


def _yf_single(ticker: str, frame: pd.DataFrame) -> pd.DataFrame:
    return pd.concat({ticker: frame}, axis=1)


def _closes(db: Session, stock_id: int) -> list[float]:
    return [
        float(r[0]) for r in db.execute(
            text("SELECT close FROM ohlcv_daily WHERE stock_id=:i ORDER BY date"),
            {"i": stock_id},
        )
    ]


# ---------------------------------------------------------------------------
# Split detection → full-history rebase
# ---------------------------------------------------------------------------

def test_split_triggers_full_rebase(db, monkeypatch):
    """Stored history at pre-split basis (400); the incremental frame's overlap
    bar comes back at 40 (10:1 split) → old bars wiped, full history re-
    downloaded on the new basis."""
    s = _seed_stock(db)
    d0 = date(2026, 6, 1)
    _store_bars(db, s.id, d0, [400.0, 402.0, 404.0])  # last stored = d0+2

    overlap = d0 + timedelta(days=2)
    incremental = _frame(overlap, [40.4, 41.0])       # overlap bar 10x off
    rebased_full = _frame(d0, [40.0, 40.2, 40.4, 41.0])

    calls: list[dict] = []

    def fake_download(tickers, **kw):
        calls.append(kw)
        # First call = the incremental batch; second = the 10y rebase fetch.
        return _yf_single("SPLT", incremental if len(calls) == 1 else rebased_full)

    monkeypatch.setattr(ohlcv_service, "_yf_download", fake_download)
    res = ohlcv_service.fetch_and_upsert(db, [s], start=overlap)
    db.commit()

    assert res.stocks_rebased == 1
    assert res.stocks_succeeded == 1
    assert len(calls) == 2
    assert calls[1].get("period") == "10y"            # rebase = full refetch
    # Entire series is now on the post-split basis — no 400s left.
    assert _closes(db, s.id) == [40.0, 40.2, 40.4, 41.0]


def test_small_close_correction_does_not_rebase(db, monkeypatch):
    """A same-date close a few % off (in-flight close self-heal) is NOT a
    split: normal upsert overwrites the bar, no extra fetch."""
    s = _seed_stock(db, "HEAL")
    d0 = date(2026, 6, 1)
    _store_bars(db, s.id, d0, [100.0, 101.0])

    overlap = d0 + timedelta(days=1)
    incremental = _frame(overlap, [98.5, 99.0])       # −2.5%: inside the band

    calls: list[dict] = []
    monkeypatch.setattr(
        ohlcv_service, "_yf_download",
        lambda tickers, **kw: (calls.append(kw), _yf_single("HEAL", incremental))[1],
    )
    res = ohlcv_service.fetch_and_upsert(db, [s], start=overlap)
    db.commit()

    assert res.stocks_rebased == 0
    assert len(calls) == 1                            # no rebase fetch
    assert _closes(db, s.id) == [100.0, 98.5, 99.0]   # overlap bar self-healed


def test_failed_rebase_keeps_old_bars(db, monkeypatch):
    """If the rebase refetch returns nothing, the old history must survive
    (never destroy data we can't replace)."""
    s = _seed_stock(db, "KEEP")
    d0 = date(2026, 6, 1)
    _store_bars(db, s.id, d0, [400.0, 402.0])

    overlap = d0 + timedelta(days=1)
    incremental = _frame(overlap, [40.2, 41.0])
    calls: list[dict] = []

    def fake_download(tickers, **kw):
        calls.append(kw)
        if len(calls) == 1:
            return _yf_single("KEEP", incremental)
        return pd.DataFrame()                          # rebase fetch: no data

    monkeypatch.setattr(ohlcv_service, "_yf_download", fake_download)
    res = ohlcv_service.fetch_and_upsert(db, [s], start=overlap)
    db.rollback()  # what the callers' chunk loop does on failure

    assert res.stocks_rebased == 0
    assert res.stocks_failed == 1
    assert _closes(db, s.id) == [400.0, 402.0]        # untouched


# ---------------------------------------------------------------------------
# Dead-ticker quarantine
# ---------------------------------------------------------------------------

def test_empty_fetch_increments_streak_and_data_resets_it(db, monkeypatch):
    s = _seed_stock(db, "DEAD")
    monkeypatch.setattr(
        ohlcv_service, "_yf_download", lambda tickers, **kw: pd.DataFrame()
    )
    for expected in (1, 2, 3):
        ohlcv_service.fetch_and_upsert(db, [s], period="10y")
        db.commit()
        assert s.ohlcv_nodata_streak == expected
    assert s.ohlcv_last_nodata_at == date.today()

    # A later fetch WITH data resets the streak.
    frame = _frame(date(2026, 6, 1), [10.0, 10.5])
    monkeypatch.setattr(
        ohlcv_service, "_yf_download", lambda tickers, **kw: _yf_single("DEAD", frame)
    )
    ohlcv_service.fetch_and_upsert(db, [s], period="10y")
    db.commit()
    assert s.ohlcv_nodata_streak == 0


def test_split_quarantined_rule(db):
    today = date(2026, 7, 4)
    fresh_fail = Stock(ticker="A1", exchange="X", name="a", country="US",
                       ohlcv_nodata_streak=2, ohlcv_last_nodata_at=today)
    quarantined = Stock(ticker="A2", exchange="X", name="b", country="US",
                        ohlcv_nodata_streak=3, ohlcv_last_nodata_at=today - timedelta(days=2))
    reprobe_due = Stock(ticker="A3", exchange="X", name="c", country="US",
                        ohlcv_nodata_streak=9, ohlcv_last_nodata_at=today - timedelta(days=8))
    healthy = Stock(ticker="A4", exchange="X", name="d", country="US")

    fetchable, quar = ohlcv_service.split_quarantined(
        [fresh_fail, quarantined, reprobe_due, healthy], today=today
    )
    assert [s.ticker for s in quar] == ["A2"]                 # streak≥3, recent
    assert [s.ticker for s in fetchable] == ["A1", "A3", "A4"]  # below bar / re-probe due / clean


def test_cron_fetch_plan_skips_quarantined_empty_stock(db, monkeypatch):
    """Integration: an empty stock in quarantine is not fetched by the cron
    plan, while a normal empty stock still gets its 10y backfill."""
    import app.core.db as db_module
    from app.scheduler.jobs import scan_alerts as job

    dead = Stock(ticker="DEADQ", exchange="X", name="dead", country="US",
                 ohlcv_nodata_streak=5, ohlcv_last_nodata_at=date.today())
    alive = Stock(ticker="NEWQ", exchange="X", name="new", country="US")
    db.add_all([dead, alive])
    db.commit()

    monkeypatch.setattr(job, "SessionLocal", db_module.SessionLocal)
    fetched: list[list[str]] = []
    monkeypatch.setattr(
        job, "fetch_and_upsert",
        lambda session, stocks, **kw: fetched.append(sorted(s.ticker for s in stocks)),
    )
    monkeypatch.setattr(
        job, "run_tracked_scan",
        lambda session, trigger, existing_run=None: None,
    )
    job.run_scan_alerts(trigger="cron")

    assert fetched == [["NEWQ"]]                       # DEADQ skipped entirely
