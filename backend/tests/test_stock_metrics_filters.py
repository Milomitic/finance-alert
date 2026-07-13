"""Screener stock_metrics filters (price/Δ%/RSI/EMA/52w/volume/mktcap/signals)
+ sort + the persist step that feeds them. The metrics are persisted at scan
end by market_stats_service; here we seed stock_metrics rows directly and assert
the search predicates + sort + response wiring behave."""
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Stock, StockMetrics
from app.services.market_stats_service import _persist_stock_metrics
from app.services.stock_service import StockFilter, search_stocks

NOW = datetime(2026, 6, 18, tzinfo=UTC)


def _stock(db: Session, ticker: str, *, market_cap=None) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, sector="Tech",
              country="US", market_cap=market_cap)
    db.add(s)
    db.flush()
    return s


def _metrics(db: Session, stock_id: int, **kw) -> None:
    db.add(StockMetrics(stock_id=stock_id, computed_at=NOW, **kw))


def _seed(db: Session) -> dict[str, int]:
    a = _stock(db, "AAA", market_cap=500_000_000_000)
    _metrics(db, a.id, last_close=100.0, change_pct=2.5, ema50=90.0, ema200=80.0,
             rsi14=75.0, high_252=102.0, low_252=40.0, vol_today=5_000_000,
             vol_avg_20=1_000_000, vol_ratio=5.0)
    b = _stock(db, "BBB", market_cap=2_000_000_000)
    _metrics(db, b.id, last_close=10.0, change_pct=-3.0, ema50=15.0, ema200=20.0,
             rsi14=25.0, high_252=50.0, low_252=9.8, vol_today=100_000,
             vol_avg_20=200_000, vol_ratio=0.5)
    c = _stock(db, "CCC", market_cap=50_000_000_000)
    _metrics(db, c.id, last_close=55.0, change_pct=0.4, ema50=50.0, ema200=60.0,
             rsi14=50.0, high_252=80.0, low_252=30.0, vol_today=300_000,
             vol_avg_20=300_000, vol_ratio=1.0)
    d = _stock(db, "DDD", market_cap=1_000_000_000)  # NO metrics row (too few bars)
    db.commit()
    return {"a": a.id, "b": b.id, "c": c.id, "d": d.id}


def _tickers(page) -> list[str]:
    return sorted(s.stock.ticker for s in page.items)


def test_no_metric_filter_keeps_metricless_stock(db: Session) -> None:
    _seed(db)
    assert "DDD" in _tickers(search_stocks(db, StockFilter()))  # LEFT JOIN


def test_price_range(db: Session) -> None:
    _seed(db)
    assert _tickers(search_stocks(db, StockFilter(price_min=50, price_max=200))) == ["AAA", "CCC"]


def test_change_min_advancers(db: Session) -> None:
    _seed(db)  # the A/D tile maps to change_min=0 (Δ% > 0)
    assert _tickers(search_stocks(db, StockFilter(change_min=0))) == ["AAA", "CCC"]


def test_rsi_oversold(db: Session) -> None:
    _seed(db)
    assert _tickers(search_stocks(db, StockFilter(rsi_max=30))) == ["BBB"]


def test_rsi_overbought(db: Session) -> None:
    _seed(db)
    assert _tickers(search_stocks(db, StockFilter(rsi_min=70))) == ["AAA"]


def test_above_ema200(db: Session) -> None:
    _seed(db)
    assert _tickers(search_stocks(db, StockFilter(above_ema200=True))) == ["AAA"]


def test_above_ema50(db: Session) -> None:
    _seed(db)  # A 100>90, C 55>50; B 10<15 excluded; D no row
    assert _tickers(search_stocks(db, StockFilter(above_ema50=True))) == ["AAA", "CCC"]


def test_near_52w_high(db: Session) -> None:
    _seed(db)  # 100 >= 0.95*102 = 96.9
    assert _tickers(search_stocks(db, StockFilter(near_52w_high=True))) == ["AAA"]


def test_near_52w_low(db: Session) -> None:
    _seed(db)  # 10 <= 1.05*9.8 = 10.29
    assert _tickers(search_stocks(db, StockFilter(near_52w_low=True))) == ["BBB"]


def test_vol_spike(db: Session) -> None:
    _seed(db)  # vol_ratio 5 > 2
    assert _tickers(search_stocks(db, StockFilter(vol_spike=True))) == ["AAA"]


def test_volume_min(db: Session) -> None:
    _seed(db)
    assert _tickers(search_stocks(db, StockFilter(volume_min=1_000_000))) == ["AAA"]


def test_market_cap_range(db: Session) -> None:
    _seed(db)
    assert _tickers(search_stocks(db, StockFilter(market_cap_min=10_000_000_000))) == ["AAA", "CCC"]


def test_has_signals(db: Session) -> None:
    ids = _seed(db)
    db.add(Alert(stock_id=ids["b"], trigger_price=1.0))            # active (triggered now)
    arch = Alert(stock_id=ids["c"], trigger_price=1.0, archived_at=NOW)  # archived → excluded
    db.add(arch)
    db.commit()
    assert _tickers(search_stocks(db, StockFilter(has_signals=True))) == ["BBB"]


# ── has_signals recency bound ────────────────────────────────────────────────
# The EXISTS is bounded on signal_date (bar date of the match), falling back
# to the triggered_at date for legacy rows. Unbounded it matched ~99% of the
# universe — every stock has SOME alert in its history.

def test_has_signals_excludes_old_signals(db: Session) -> None:
    from datetime import date, timedelta
    ids = _seed(db)
    old = date.today() - timedelta(days=30)
    db.add(Alert(stock_id=ids["a"], trigger_price=1.0, signal_date=old))
    db.add(Alert(stock_id=ids["b"], trigger_price=1.0, signal_date=date.today()))
    db.commit()
    # Default window (7 days): only the fresh signal survives.
    assert _tickers(search_stocks(db, StockFilter(has_signals=True))) == ["BBB"]
    # Widening the window to 60 days re-includes the old one.
    assert _tickers(search_stocks(
        db, StockFilter(has_signals=True, signals_within_days=60)
    )) == ["AAA", "BBB"]


def test_has_signals_legacy_null_signal_date_falls_back_to_triggered_at(db: Session) -> None:
    from datetime import timedelta
    ids = _seed(db)
    # Legacy alert: signal_date NULL, triggered long ago → excluded.
    db.add(Alert(stock_id=ids["a"], trigger_price=1.0,
                 triggered_at=datetime.now(UTC) - timedelta(days=60)))
    # Legacy alert triggered now → the triggered_at fallback keeps it.
    db.add(Alert(stock_id=ids["b"], trigger_price=1.0,
                 triggered_at=datetime.now(UTC)))
    db.commit()
    assert _tickers(search_stocks(db, StockFilter(has_signals=True))) == ["BBB"]


def test_has_signals_window_clamped_defensively(db: Session) -> None:
    """The API validates 1..90 (422); the service clamps out-of-range values
    instead of emitting a nonsense cutoff when called directly."""
    from datetime import date, timedelta
    ids = _seed(db)
    db.add(Alert(stock_id=ids["a"], trigger_price=1.0,
                 signal_date=date.today() - timedelta(days=80)))
    db.commit()
    # 5000 clamps to 90 → the 80-day-old signal is still inside the window.
    assert _tickers(search_stocks(
        db, StockFilter(has_signals=True, signals_within_days=5000)
    )) == ["AAA"]
    # 0 clamps to 1 (no crash, tightest window).
    assert _tickers(search_stocks(
        db, StockFilter(has_signals=True, signals_within_days=0)
    )) == []


def test_sort_by_price_desc_nulls_last(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(sort_by="price", sort_dir="desc"))
    ordered = [s.stock.ticker for s in page.items]
    assert ordered[:3] == ["AAA", "CCC", "BBB"]  # 100 > 55 > 10; DDD (NULL) last


def test_sort_by_vol_today_desc_and_asc_nulls_last(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(sort_by="vol_today", sort_dir="desc"))
    assert [s.stock.ticker for s in page.items] == ["AAA", "CCC", "BBB", "DDD"]
    # Ascending must NOT lead with the metricless row (NULLS LAST).
    page = search_stocks(db, StockFilter(sort_by="vol_today", sort_dir="asc"))
    assert [s.stock.ticker for s in page.items] == ["BBB", "CCC", "AAA", "DDD"]


def test_metrics_in_response(db: Session) -> None:
    _seed(db)
    m = search_stocks(db, StockFilter(q="AAA")).items[0].metrics
    assert m.last_close == 100.0 and m.rsi14 == 75.0 and m.vol_ratio == 5.0
    # Raw volume pair surfaced for the screener's Volume column.
    assert m.vol_today == 5_000_000 and m.vol_avg_20 == 1_000_000


def test_persist_skips_metricless_and_writes_rows(db: Session) -> None:
    s1 = _stock(db, "ZZZ")
    s2 = _stock(db, "YYY")
    db.commit()
    metrics = [
        SimpleNamespace(stock_id=s1.id, last_close=12.0, change_pct=1.0, ema50=11.0,
                        ema200=10.0, rsi14=55.0, high_252=15.0, low_252=8.0,
                        vol_today=123, vol_avg_20=100.0, vol_ratio=1.23),
        SimpleNamespace(stock_id=s2.id, last_close=None, change_pct=None, ema50=None,
                        ema200=None, rsi14=None, high_252=None, low_252=None,
                        vol_today=None, vol_avg_20=None, vol_ratio=None),
    ]
    _persist_stock_metrics(db, metrics)
    db.commit()
    rows = db.execute(select(StockMetrics)).scalars().all()
    assert len(rows) == 1  # YYY skipped (no close)
    assert rows[0].stock_id == s1.id and rows[0].rsi14 == 55.0
