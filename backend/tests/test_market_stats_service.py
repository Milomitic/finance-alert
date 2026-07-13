"""Tests for app.services.market_stats_service."""

from app.services.market_stats_service import (
    StockMetrics,
    compute_stock_metrics,
    derive_mood,
)
from tests.conftest_market import build_ohlcv, build_ohlcv_volume_spike


def test_compute_metrics_full_data():
    ohlcv = build_ohlcv(n_bars=250, start_close=100.0, drift=0.1)
    m = compute_stock_metrics(
        stock_id=1, ticker="X", name="X Inc", sector="Tech",
        index_codes=["NDX"], market_cap=1_000_000_000.0, ohlcv=ohlcv,
    )
    assert m is not None
    assert m.has_full_data is True
    assert m.bars_count == 250
    assert m.last_close == 100.0 + 0.1 * 249
    assert m.prev_close == 100.0 + 0.1 * 248
    assert m.change_pct is not None and m.change_pct > 0
    assert m.ema50 is not None
    assert m.ema200 is not None
    assert m.rsi14 is not None
    assert m.high_252 == m.last_close       # ascending series → max is last
    assert m.new_52w_high is True
    assert m.new_52w_low is False
    assert m.near_52w_high is True


def test_compute_metrics_short_history_partial():
    """Short history → still produces metrics, but `has_full_data=False`
    keeps the row out of the breadth aggregate.

    Note on EMA semantics (May 2026 SMA→EMA switch): unlike SMA, EMA has
    no warmup NaN — it initialises to the first close and converges with
    weight 2/(N+1) per bar. So `ema200` is a number even with 30 bars
    (just heavily weighted toward those 30). The guarantee the breadth
    aggregate cares about — "don't count this stock in pct_above_ema200
    when it's too short to be meaningful" — is preserved via the
    `has_full_data` flag, which still requires bars >= 200.
    """
    ohlcv = build_ohlcv(n_bars=30, start_close=100.0, drift=0.1)
    m = compute_stock_metrics(
        stock_id=2, ticker="Y", name="Y Corp", sector=None,
        index_codes=[], market_cap=None, ohlcv=ohlcv,
    )
    assert m is not None
    assert m.has_full_data is False         # bars < 200 → excluded from breadth
    # EMA50 / EMA200 are numbers (not None) thanks to ewm's no-warmup
    # behaviour. The breadth aggregate uses `has_full_data` as its real
    # gate; the ema values themselves can still be inspected.
    assert m.ema50 is not None
    assert m.ema200 is not None
    assert m.rsi14 is not None              # 30 bars enough for RSI14
    assert m.vol_avg_20 is not None         # 30 bars enough for 20-day avg


def test_compute_metrics_too_short_returns_none():
    ohlcv = build_ohlcv(n_bars=10)
    m = compute_stock_metrics(1, "Z", "Z Ltd", None, [], None, ohlcv)
    assert m is None


def test_compute_metrics_volume_spike():
    ohlcv = build_ohlcv_volume_spike(n_bars=30)
    m = compute_stock_metrics(1, "V", "V Corp", None, [], None, ohlcv)
    assert m is not None
    assert m.vol_ratio is not None and m.vol_ratio > 4.0


def test_derive_mood_bullish():
    assert derive_mood(pct_above_ema200=65.0, advancers=130, decliners=70) == "bullish"


def test_derive_mood_bearish():
    assert derive_mood(pct_above_ema200=35.0, advancers=70, decliners=130) == "bearish"


def test_derive_mood_neutral_by_breadth():
    assert derive_mood(pct_above_ema200=50.0, advancers=130, decliners=70) == "neutral"


def test_derive_mood_neutral_by_advancers():
    # high breadth but more decliners → neutral
    assert derive_mood(pct_above_ema200=70.0, advancers=80, decliners=120) == "neutral"


from app.services.market_stats_service import (
    aggregate_by_index,
    aggregate_by_sector,
    aggregate_global,
)


def _metric(stock_id, ticker, *, sector=None, indices=None, change_pct=0.5,
            ema50=99.0, ema200=95.0, rsi14=50.0, near_high=False, near_low=False,
            new_high=False, new_low=False, vol_ratio=1.0, has_full=True,
            last_close=100.0):
    return StockMetrics(
        stock_id=stock_id, ticker=ticker, name=ticker, sector=sector,
        index_codes=indices or [], market_cap=1e9, bars_count=250,
        last_close=last_close, prev_close=last_close - 1.0,
        change_pct=change_pct, ema50=ema50, ema200=ema200, rsi14=rsi14,
        high_252=last_close, low_252=last_close - 10.0,
        near_52w_high=near_high, near_52w_low=near_low,
        new_52w_high=new_high, new_52w_low=new_low,
        vol_today=1_000_000, vol_avg_20=500_000.0, vol_ratio=vol_ratio,
        has_full_data=has_full,
    )


def test_aggregate_global_breadth():
    ms = [
        _metric(1, "A", change_pct=1.0, ema200=99.0, last_close=100.0, rsi14=72.0),
        _metric(2, "B", change_pct=-0.5, ema200=99.0, last_close=98.0, rsi14=25.0),
        _metric(3, "C", change_pct=2.0, ema200=99.0, last_close=110.0, rsi14=55.0),
    ]
    g = aggregate_global(ms)
    assert g["stocks_total"] == 3
    assert g["stocks_with_data"] == 3
    assert g["advancers"] == 2
    assert g["decliners"] == 1
    # 2 of 3 above ema200 (A: 100>99 ✓, B: 98<99 ✗, C: 110>99 ✓)
    assert g["pct_above_ema200"] == 66.7
    assert g["rsi_oversold_count"] == 1
    assert g["rsi_overbought_count"] == 1


def test_aggregate_global_empty():
    g = aggregate_global([])
    assert g["stocks_total"] == 0
    assert g["mood"] == "neutral"


def test_aggregate_by_index_buckets():
    ms = [
        _metric(1, "A", indices=["NDX", "SP500"], change_pct=1.0, ema200=90.0, last_close=100.0),
        _metric(2, "B", indices=["NDX"], change_pct=-1.0, ema200=99.0, last_close=98.0, new_low=True),
        _metric(3, "C", indices=["SSE50"], change_pct=2.0, ema200=99.0, last_close=110.0, vol_ratio=3.0),
    ]
    rows = aggregate_by_index(ms, [("NDX", "Nasdaq"), ("SP500", "S&P"), ("SSE50", "SSE"), ("DJI", "Dow")])
    by_code = {r["code"]: r for r in rows}
    assert by_code["NDX"]["n"] == 2
    assert by_code["SP500"]["n"] == 1
    assert by_code["SSE50"]["n"] == 1
    assert by_code["DJI"]["n"] == 0
    assert by_code["DJI"]["pct_above_ema200"] is None    # empty bucket
    assert by_code["NDX"]["new_52w_lows"] == 1
    assert by_code["SSE50"]["volume_spikes_count"] == 1


def test_aggregate_by_sector_sorted_by_avg_change():
    ms = [
        _metric(1, "A", sector="Tech", change_pct=2.0),
        _metric(2, "B", sector="Tech", change_pct=1.0),
        _metric(3, "C", sector="Energy", change_pct=-1.5),
        _metric(4, "D", sector="Finance", change_pct=0.5),
    ]
    rows = aggregate_by_sector(ms)
    assert [r["sector"] for r in rows] == ["Tech", "Finance", "Energy"]
    assert rows[0]["n_stocks"] == 2
    assert rows[0]["avg_change_pct"] == 1.5


from app.services.market_stats_service import (
    build_movers,
    build_rsi_distribution,
    build_treemap,
)


def test_build_movers_ordering():
    ms = [
        _metric(1, "A", change_pct=2.0),
        _metric(2, "B", change_pct=-3.0),
        _metric(3, "C", change_pct=1.0),
        _metric(4, "D", change_pct=-1.5),
    ]
    out = build_movers(ms, top_n=2)
    assert [r["ticker"] for r in out["gainers"]] == ["A", "C"]
    assert [r["ticker"] for r in out["losers"]] == ["B", "D"]


def test_build_movers_volume_spikes():
    ms = [
        _metric(1, "A", vol_ratio=1.0),
        _metric(2, "B", vol_ratio=4.5),
        _metric(3, "C", vol_ratio=2.5),
    ]
    out = build_movers(ms)
    assert out["volume_spikes"][0]["ticker"] == "B"
    assert out["volume_spikes"][0]["vol_ratio"] == 4.5


def test_build_rsi_distribution_binning():
    ms = [
        _metric(1, "A", rsi14=5.0),     # bin 0
        _metric(2, "B", rsi14=25.0),    # bin 2 (oversold edge)
        _metric(3, "C", rsi14=50.0),    # bin 5
        _metric(4, "D", rsi14=72.0, indices=["NDX"]),    # bin 7 (overbought)
        _metric(5, "E", rsi14=99.9, indices=["NDX"]),   # bin 9
    ]
    dist = build_rsi_distribution(ms, indices=[("NDX", "Nasdaq"), ("SP500", "S&P")])
    assert dist["all"] == [1, 0, 1, 0, 0, 1, 0, 1, 0, 1]
    assert dist["by_index"]["NDX"] == [0, 0, 0, 0, 0, 0, 0, 1, 0, 1]
    assert dist["by_index"]["SP500"] == [0] * 10


def test_build_treemap_filters_no_marketcap():
    ms = [
        _metric(1, "A", change_pct=1.0),                                      # has cap
        StockMetrics(stock_id=2, ticker="B", name="B Corp", sector=None, index_codes=[],
                     market_cap=None,                                         # no cap → excluded
                     bars_count=250, last_close=10.0, prev_close=9.5,
                     change_pct=1.0, ema50=None, ema200=None, rsi14=None,
                     high_252=None, low_252=None,
                     near_52w_high=False, near_52w_low=False,
                     new_52w_high=False, new_52w_low=False,
                     vol_today=0, vol_avg_20=None, vol_ratio=None, has_full_data=False),
    ]
    out = build_treemap(ms)
    assert len(out) == 1
    assert out[0]["ticker"] == "A"


import json as _json

from app.models import Index, MarketSnapshot, OhlcvDaily, Stock
from app.models.index import StockIndex
from app.services.market_stats_service import get_latest_snapshot, recompute_snapshot


def _seed_basic(session, *, n_stocks=3, n_bars=250):
    """Seed indices + stocks + OHLCV for integration testing.
    Note: Stock.market_cap is BigInteger so we use int values.
    """
    idx_ndx = Index(code="NDX", name="Nasdaq-100")
    idx_sp = Index(code="SP500", name="S&P 500")
    session.add_all([idx_ndx, idx_sp])
    session.flush()

    base_ohlcv = build_ohlcv(n_bars=n_bars, start_close=100.0, drift=0.1)
    for i in range(n_stocks):
        s = Stock(
            ticker=f"T{i}", exchange="NMS", name=f"Stock {i}",
            sector="Technology" if i % 2 == 0 else "Energy",
            market_cap=int(1e9) + i * int(1e8),
        )
        session.add(s)
        session.flush()
        # All in NDX, every other also in SP500
        session.add(StockIndex(stock_id=s.id, index_id=idx_ndx.id))
        if i % 2 == 0:
            session.add(StockIndex(stock_id=s.id, index_id=idx_sp.id))
        for _, row in base_ohlcv.iterrows():
            session.add(OhlcvDaily(
                stock_id=s.id, date=row["date"],
                open=row["open"], high=row["high"], low=row["low"],
                close=row["close"], volume=row["volume"],
            ))
    session.commit()


def test_recompute_snapshot_creates_row(db):
    _seed_basic(db, n_stocks=3, n_bars=250)
    snap = recompute_snapshot(db)
    assert snap.id == 1
    assert snap.stocks_total == 3
    payload = _json.loads(snap.payload)
    assert payload["global"]["stocks_total"] == 3
    assert len(payload["by_index"]) >= 2     # NDX + SP500
    by_code = {r["code"]: r for r in payload["by_index"]}
    assert by_code["NDX"]["n"] == 3
    assert by_code["SP500"]["n"] == 2


def test_recompute_snapshot_idempotent(db):
    """Calling twice keeps a single row, second overwrites payload."""
    _seed_basic(db, n_stocks=2, n_bars=210)
    s1 = recompute_snapshot(db, scan_run_id=None)
    s2 = recompute_snapshot(db, scan_run_id=None)
    rows = db.query(MarketSnapshot).all()
    assert len(rows) == 1
    assert s2.computed_at >= s1.computed_at


def test_get_latest_snapshot_none_when_empty(db):
    assert get_latest_snapshot(db) is None


def test_get_latest_snapshot_returns_row(db):
    _seed_basic(db, n_stocks=1, n_bars=210)
    recompute_snapshot(db)
    snap = get_latest_snapshot(db)
    assert snap is not None and snap.id == 1


from app.services import market_stats_service, scan_runner


def test_scan_runner_recomputes_snapshot(db, monkeypatch):
    """run_tracked_scan invokes recompute_snapshot at the end."""
    _seed_basic(db, n_stocks=2, n_bars=210)

    # Stub scan_universe to avoid the full alert evaluation pipeline
    from app.services import scan_service
    monkeypatch.setattr(
        scan_service,
        "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=2, stocks_skipped=0, alerts_fired=0, states_updated=0
        ),
    )

    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"
    snap = market_stats_service.get_latest_snapshot(db)
    assert snap is not None
    assert snap.scan_run_id == run.id


def test_scan_runner_recompute_failure_is_non_fatal(db, monkeypatch):
    """If recompute_snapshot raises, scan still finishes successfully."""
    _seed_basic(db, n_stocks=1, n_bars=210)

    from app.services import scan_service
    monkeypatch.setattr(
        scan_service,
        "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=1, stocks_skipped=0, alerts_fired=0, states_updated=0
        ),
    )

    def _boom(db, scan_run_id=None):
        raise RuntimeError("boom")
    monkeypatch.setattr(market_stats_service, "recompute_snapshot", _boom)

    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"      # snapshot failure must not mark scan failed
    assert run.completed_at is not None
