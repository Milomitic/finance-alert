"""Snapshot of L1 cache state + L2 row counts + DB file size.
Pure read; no side effects on the cache or DB."""
import time

from app.services import cache_metrics, stock_fundamentals_service, stock_news_service


def test_snapshot_shape_on_empty_caches(db):
    # Clear the L1 dicts so we have a deterministic baseline. Don't touch L2.
    stock_fundamentals_service._CACHE.clear()
    stock_news_service._CACHE.clear()

    snap = cache_metrics.snapshot()

    assert set(snap.keys()) == {"fundamentals", "news", "db", "ohlcv"}
    assert snap["fundamentals"]["l1_entries"] == 0
    assert snap["news"]["l1_entries"] == 0
    assert snap["fundamentals"]["oldest_age_s"] is None
    assert snap["fundamentals"]["newest_age_s"] is None
    assert snap["news"]["oldest_age_s"] is None
    assert isinstance(snap["fundamentals"]["l2_entries"], int)
    assert snap["fundamentals"]["l2_entries"] >= 0
    # L2 freshness keys present (None or numeric depending on DB contents).
    assert "l2_oldest_age_s" in snap["fundamentals"]
    assert "l2_newest_age_s" in snap["fundamentals"]
    assert isinstance(snap["db"]["size_mb"], float)
    # OHLCV freshness row (SAL-2): MAX(date) + count-at-max, memoized 60s.
    assert set(snap["ohlcv"].keys()) == {"max_date", "stocks_at_max"}
    assert isinstance(snap["ohlcv"]["stocks_at_max"], int)


def test_ohlcv_freshness_reads_max_date_and_count(db):
    """One bar per stock on the newest date → n = stocks at MAX(date)."""
    from datetime import date

    from app.models import OhlcvDaily, Stock

    cache_metrics.reset_ohlcv_cache()          # drop any memo from other tests
    s1 = Stock(ticker="AAA", name="A", exchange="NYSE")
    s2 = Stock(ticker="BBB", name="B", exchange="NYSE")
    db.add_all([s1, s2])
    db.flush()
    mk = lambda sid, d: OhlcvDaily(  # noqa: E731 — compact fixture row
        stock_id=sid, date=d, open=1, high=1, low=1, close=1, volume=100,
    )
    db.add_all([
        mk(s1.id, date(2026, 7, 6)),
        mk(s1.id, date(2026, 7, 7)),
        mk(s2.id, date(2026, 7, 7)),
    ])
    db.commit()

    fresh = cache_metrics._ohlcv_freshness()
    assert fresh["max_date"] == "2026-07-07"
    assert fresh["stocks_at_max"] == 2

    cache_metrics.reset_ohlcv_cache()          # don't leak the memo onward


def test_snapshot_reflects_l1_entries(db):
    stock_fundamentals_service._CACHE.clear()
    from app.services.stock_fundamentals_service import Fundamentals
    stock_fundamentals_service._CACHE["FAKE"] = Fundamentals(
        ticker="FAKE", fetched_at=time.time() - 30.0
    )

    snap = cache_metrics.snapshot()

    assert snap["fundamentals"]["l1_entries"] == 1
    assert snap["fundamentals"]["oldest_age_s"] is not None
    assert snap["fundamentals"]["oldest_age_s"] >= 30.0


def test_snapshot_oldest_age_is_oldest_not_newest(db):
    stock_fundamentals_service._CACHE.clear()
    from app.services.stock_fundamentals_service import Fundamentals
    now = time.time()
    stock_fundamentals_service._CACHE["A"] = Fundamentals(ticker="A", fetched_at=now - 100.0)
    stock_fundamentals_service._CACHE["B"] = Fundamentals(ticker="B", fetched_at=now - 5.0)

    snap = cache_metrics.snapshot()

    assert snap["fundamentals"]["oldest_age_s"] >= 100.0


def test_snapshot_newest_age_is_newest_not_oldest(db):
    stock_fundamentals_service._CACHE.clear()
    from app.services.stock_fundamentals_service import Fundamentals
    now = time.time()
    stock_fundamentals_service._CACHE["A"] = Fundamentals(ticker="A", fetched_at=now - 100.0)
    stock_fundamentals_service._CACHE["B"] = Fundamentals(ticker="B", fetched_at=now - 5.0)

    snap = cache_metrics.snapshot()

    # newest = freshest entry → the 5s-old one, not the 100s-old one.
    assert snap["fundamentals"]["newest_age_s"] >= 5.0
    assert snap["fundamentals"]["newest_age_s"] < 100.0
