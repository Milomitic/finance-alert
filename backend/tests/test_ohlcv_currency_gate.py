"""Pence/pounds currency gate on the OHLCV ingest.

The scaling decision used to make one uncached fast_info HTTP call per stock
per fetch (~999/scan, though only .L listings can be GBp) and FAILED OPEN: a
transient lookup error on a GBp stock stored raw pence (100× too high) over
previously-correct pounds rows. Now: non-.L tickers skip the lookup entirely,
successful .L lookups are memoized, and a failed .L lookup skips the stock's
upsert for this cycle (fail CLOSED).
"""

import pandas as pd
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
    ins, _ = ohlcv_service._upsert_one_stock(db, stock, _frame())
    db.commit()
    assert ins == 0
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
