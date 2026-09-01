"""Pence/pounds currency gate on the OHLCV ingest.

The scaling decision used to make one uncached fast_info HTTP call per stock
per fetch (~999/scan, though only .L listings can be GBp) and FAILED OPEN: a
transient lookup error on a GBp stock stored raw pence (100× too high) over
previously-correct pounds rows. Now: non-.L tickers skip the lookup entirely,
successful .L lookups are memoized, and a failed .L lookup skips the stock's
upsert for this cycle (fail CLOSED).
"""

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Stock
from app.services import currency_units, ohlcv_service


def _frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=2, freq="D")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [1_000_000] * 2,
        },
        index=dates,
    )


def _seed(db: Session, ticker: str, exchange: str = "NASDAQ") -> Stock:
    s = Stock(ticker=ticker, exchange=exchange, name=ticker, country="US")
    db.add(s)
    db.commit()
    return s


def _bars(db: Session, stock_id: int) -> list[tuple]:
    return db.execute(
        text("SELECT date, close FROM ohlcv_daily WHERE stock_id = :i ORDER BY date"),
        {"i": stock_id},
    ).fetchall()


def test_non_lse_ticker_never_calls_currency_lookup(db, monkeypatch):
    def boom(ticker):
        raise AssertionError("currency lookup must not run for non-.L tickers")

    monkeypatch.setattr(currency_units, "get_native_currency", boom)
    stock = _seed(db, "AAPL")
    ins, _ = ohlcv_service._upsert_one_stock(db, stock, _frame())
    db.commit()
    assert ins == 2
    assert [float(r[1]) for r in _bars(db, stock.id)] == [100.5, 101.5]  # unscaled


def test_lse_lookup_failure_fails_closed(db, monkeypatch):
    monkeypatch.setattr(
        currency_units, "get_native_currency", lambda t: None
    )
    currency_units._CURRENCY_CACHE.clear()
    stock = _seed(db, "BARC.L", exchange="LSE")
    # RAISES since 2026-09-01, and the raise is the point. It used to return
    # (0, 0), which the fetch loop could not tell apart from "already up to
    # date": it reset the no-data streak and counted the stock as succeeded,
    # so a persistent lookup failure would have frozen the ~100 LSE names
    # while the dashboard reported a clean batch.
    with pytest.raises(ohlcv_service.CurrencyGateSkipped):
        ohlcv_service._upsert_one_stock(db, stock, _frame())
    db.rollback()
    assert _bars(db, stock.id) == []  # nothing written — no pence/pounds gamble


def test_lse_gbp_pence_scaled_and_memoized(db, monkeypatch):
    lookups: list[str] = []

    def fake_lookup(ticker):
        lookups.append(ticker)
        return "GBp"

    monkeypatch.setattr(currency_units, "get_native_currency", fake_lookup)
    currency_units._CURRENCY_CACHE.clear()
    stock = _seed(db, "TSCO.L", exchange="LSE")
    ohlcv_service._upsert_one_stock(db, stock, _frame())
    ohlcv_service._upsert_one_stock(db, stock, _frame())  # second fetch
    db.commit()
    assert lookups == ["TSCO.L"]                          # memoized after first
    assert [float(r[1]) for r in _bars(db, stock.id)] == [1.005, 1.015]  # /100
    currency_units._CURRENCY_CACHE.clear()


def test_a_skipped_stock_is_counted_failed_and_keeps_its_streak(db, monkeypatch):
    """THE BUG THE RAISE EXISTS FOR.

    The gate fails closed correctly — nothing is written. It used to signal
    that with `return 0, 0`, which the fetch loop read as "already up to
    date": it reset `ohlcv_nodata_streak` to zero and incremented
    `stocks_succeeded`. A persistent lookup failure on the ~100 LSE names
    would therefore have frozen their prices indefinitely while the Salute
    dashboard reported a clean batch and the quarantine never engaged.

    Same family as the stale-frame bug of 2026-08-27, through a different
    door: there a stale frame proved liveness it should not have, here a
    skipped write claimed a success it had not earned.
    """
    monkeypatch.setattr(currency_units, "get_native_currency", lambda t: None)
    currency_units._CURRENCY_CACHE.clear()
    stock = _seed(db, "VOD.L", exchange="LSE")
    stock.ohlcv_nodata_streak = 2
    db.commit()

    # yfinance returns a column MultiIndex for a batch download; building it
    # here rather than borrowing a helper from another test module. Written
    # first with an undefined name, which raised inside the lambda, was caught
    # by the batch-level handler, and made this test PASS on the
    # download-failure path instead of the currency gate — green for the wrong
    # reason, which is worse than red.
    raw = _frame()
    multi = raw.copy()
    multi.columns = pd.MultiIndex.from_product([["VOD.L"], raw.columns])
    monkeypatch.setattr(ohlcv_service, "_yf_download", lambda tickers, **kw: multi)
    result = ohlcv_service.fetch_and_upsert(db, [stock], period="1mo")
    db.commit()

    assert result.stocks_failed == 1
    assert result.stocks_succeeded == 0
    assert "VOD.L" in result.failed_tickers
    # NOT reset to 0 — a run of these must reach the quarantine threshold.
    assert stock.ohlcv_nodata_streak == 2
    assert _bars(db, stock.id) == []
