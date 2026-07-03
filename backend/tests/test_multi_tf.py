"""multi-tf-kpis: the per-timeframe fetches are parallelized for the yfinance
(intraday) timeframes while DB-backed ones stay on the calling thread.

Guards: (1) output order still matches VALID_TIMEFRAMES; (2) the Session is
never handed to a worker thread (yfinance timeframes are fetched with no db);
(3) every timeframe is computed exactly once."""
from __future__ import annotations

from types import SimpleNamespace

from app.api import multi_tf
from app.services.timeframe_service import _INTRADAY, VALID_TIMEFRAMES


def _fake_kpis(tf: str) -> SimpleNamespace:
    return SimpleNamespace(
        timeframe=tf, bars=1, last_close=1.0, rsi=None, rsi_tone="n",
        ema20=None, ema50=None, ema200=None,
        ema20_above=None, ema50_above=None, ema200_above=None,
        bb_upper=None, bb_middle=None, bb_lower=None, bb_position=None,
        macd_line=None, macd_signal=None, macd_hist=None, macd_tone="n",
        composite_score=0, composite_label="x",
    )


def test_stock_path_parallelizes_only_yfinance_timeframes(monkeypatch):
    seen: list[tuple[str, bool]] = []  # (timeframe, db_was_passed)

    def fake_fetch(*, ticker, timeframe, db=None, stock=None):
        seen.append((timeframe, db is not None))
        return [timeframe]  # stand-in bars

    monkeypatch.setattr(multi_tf, "fetch_bars", fake_fetch)
    monkeypatch.setattr(multi_tf, "compute_timeframe_kpis", lambda bars, tf: _fake_kpis(tf))

    sentinel_db = object()
    items = multi_tf._compute_multi_tf("AAPL", db=sentinel_db, stock=object())

    # Order preserved regardless of parallel completion order.
    assert [it.timeframe for it in items] == list(VALID_TIMEFRAMES)
    # Every timeframe fetched exactly once.
    assert sorted(tf for tf, _ in seen) == sorted(VALID_TIMEFRAMES)
    # Intraday (yfinance) timeframes fetched WITHOUT db; daily WITH db.
    by_tf = dict(seen)
    for tf in VALID_TIMEFRAMES:
        assert by_tf[tf] is (tf not in _INTRADAY)


def test_market_path_has_no_db(monkeypatch):
    seen: list[tuple[str, bool]] = []

    def fake_fetch(*, ticker, timeframe, db=None, stock=None):
        seen.append((timeframe, db is not None))
        return [timeframe]

    monkeypatch.setattr(multi_tf, "fetch_bars", fake_fetch)
    monkeypatch.setattr(multi_tf, "compute_timeframe_kpis", lambda bars, tf: _fake_kpis(tf))

    items = multi_tf._compute_multi_tf("^GSPC")  # no db
    assert [it.timeframe for it in items] == list(VALID_TIMEFRAMES)
    # A market symbol never has a db → no worker ever receives one.
    assert all(db_passed is False for _, db_passed in seen)
