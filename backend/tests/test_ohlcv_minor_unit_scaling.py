"""Tests for ohlcv_service._normalize_minor_unit_value and its application
in _upsert_one_stock.

The helper mirrors live_quote_service._scale_pence_to_pounds: when the
yfinance native currency is GBp or GBX, divide by 100 to bring values
back to pounds. yfinance returns LSE quotes in pence (e.g., HSBA.L = 1359.4)
which need to be normalized before storage so consumer code (chart,
indicators, prev_close override, score, alerts) is automatically correct.

Why query yfinance for currency instead of trusting Stock.currency:
the catalog normalizes Stock.currency to 'GBP' uniformly for both
GBp-priced (most .L) and GBP-priced (CPG.L, IHG.L, MTLN.L per audit)
LSE stocks. Only yfinance fast_info.currency keeps the raw 'GBp' / 'GBP'
distinction we need at ingest time.
"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import ohlcv_service


@pytest.fixture(autouse=True)
def _clear_currency_memo():
    """Successful lookups are memoized per ticker for the process lifetime;
    keep tests order-independent."""
    ohlcv_service._CURRENCY_CACHE.clear()
    yield
    ohlcv_service._CURRENCY_CACHE.clear()


# ---- _normalize_minor_unit_value (pure helper) -----------------

def test_gbp_lowercase_p_scales_to_pounds() -> None:
    assert ohlcv_service._normalize_minor_unit_value("GBp", 1359.4) == pytest.approx(13.594)


def test_gbx_uppercase_alias_also_scales() -> None:
    assert ohlcv_service._normalize_minor_unit_value("GBX", 1000.0) == 10.0


def test_gbp_uppercase_pounds_passes_through() -> None:
    # Mainboard GBP (e.g., CPG.L, IHG.L) -- already in pounds.
    assert ohlcv_service._normalize_minor_unit_value("GBP", 13.59) == 13.59


def test_usd_passes_through() -> None:
    assert ohlcv_service._normalize_minor_unit_value("USD", 150.0) == 150.0


def test_none_currency_passes_through() -> None:
    # Defensive: when currency lookup fails, do NOT scale (fail-safe -- better
    # to have unscaled values than incorrectly scaled ones).
    assert ohlcv_service._normalize_minor_unit_value(None, 150.0) == 150.0


def test_none_value_returns_none() -> None:
    assert ohlcv_service._normalize_minor_unit_value("GBp", None) is None


# ---- _get_yfinance_native_currency ------------------------------

def test_get_yfinance_native_currency_returns_currency_string() -> None:
    fake_fast_info = MagicMock()
    fake_fast_info.get = MagicMock(side_effect=lambda k, *args: {"currency": "GBp"}.get(k))
    fake_ticker = MagicMock()
    fake_ticker.fast_info = fake_fast_info

    with patch("yfinance.Ticker", return_value=fake_ticker):
        currency = ohlcv_service._get_yfinance_native_currency("IAG.L")
    assert currency == "GBp"


def test_get_yfinance_native_currency_returns_none_on_error() -> None:
    """When yfinance throws (rate-limit, network, etc.), helper returns None
    so the caller can fail-safe (don't scale)."""
    with patch("yfinance.Ticker", side_effect=RuntimeError("rate limit")):
        currency = ohlcv_service._get_yfinance_native_currency("IAG.L")
    assert currency is None


# ---- _upsert_one_stock with scaler ------------------------------

def _make_pence_frame() -> pd.DataFrame:
    """Synthetic yfinance frame in pence units (LSE-style)."""
    return pd.DataFrame({
        "Open": [320.0, 322.5, 325.0],
        "High": [325.0, 327.0, 330.0],
        "Low":  [318.0, 321.0, 324.0],
        "Close": [322.5, 325.0, 328.0],
        "Volume": [1_000_000, 1_100_000, 950_000],
    }, index=pd.date_range("2026-04-01", periods=3, freq="D"))


def test_upsert_scales_pence_when_yfinance_currency_is_gbp_minor(db: Session) -> None:
    """Given yfinance returns currency='GBp' for a .L ticker, the upsert
    should scale O/H/L/C by /100 before INSERT."""
    stock = Stock(ticker="IAG_TEST.L", exchange="LSE", name="IAG Test",
                  sector="Industrials", country="GB", currency="GBP")
    db.add(stock); db.commit()

    frame = _make_pence_frame()

    with patch.object(ohlcv_service, "_get_yfinance_native_currency", return_value="GBp"):
        ohlcv_service._upsert_one_stock(db, stock, frame)
        db.commit()

    bars = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).all()
    assert len(bars) == 3
    closes = sorted([float(b.close) for b in bars])
    # 322.5 pence -> 3.225 pounds
    assert closes == pytest.approx([3.225, 3.25, 3.28])


def test_upsert_passes_through_when_yfinance_currency_is_usd(db: Session) -> None:
    """US ticker (yfinance currency='USD') should NOT be scaled."""
    stock = Stock(ticker="AAPL_TEST", exchange="NASDAQ", name="Apple Test",
                  sector="Technology", country="US", currency="USD")
    db.add(stock); db.commit()

    frame = pd.DataFrame({
        "Open": [180.0], "High": [182.0], "Low": [179.0],
        "Close": [181.5], "Volume": [50_000_000],
    }, index=pd.date_range("2026-05-01", periods=1, freq="D"))

    with patch.object(ohlcv_service, "_get_yfinance_native_currency", return_value="USD"):
        ohlcv_service._upsert_one_stock(db, stock, frame)
        db.commit()

    bar = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).one()
    assert float(bar.close) == 181.5  # unchanged


def test_upsert_passes_through_when_yfinance_returns_gbp_uppercase(db: Session) -> None:
    """Edge case: CPG.L / IHG.L / MTLN.L return currency='GBP' (not GBp)
    from yfinance. They're already in pounds, must NOT be scaled."""
    stock = Stock(ticker="CPG_TEST.L", exchange="LSE", name="Compass",
                  sector="Consumer Discretionary", country="GB", currency="GBP")
    db.add(stock); db.commit()

    # Frame contains pounds-scale values
    frame = pd.DataFrame({
        "Open": [29.30], "High": [29.50], "Low": [29.10],
        "Close": [29.40], "Volume": [5_000_000],
    }, index=pd.date_range("2026-05-01", periods=1, freq="D"))

    with patch.object(ohlcv_service, "_get_yfinance_native_currency", return_value="GBP"):
        ohlcv_service._upsert_one_stock(db, stock, frame)
        db.commit()

    bar = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).one()
    assert float(bar.close) == 29.40  # unchanged


def test_upsert_fails_closed_when_yfinance_currency_unavailable(db: Session) -> None:
    """If the currency lookup fails for a .L ticker, SKIP the stock this cycle
    (fail CLOSED). The old fail-open pass-through stored raw pence — 100× too
    high — over previously-correct pounds rows whenever the lookup transiently
    failed for a genuinely GBp-priced stock. Skipping costs one scan cycle;
    the next fetch retries the lookup (failures are not memoized)."""
    stock = Stock(ticker="UNKNOWN.L", exchange="LSE", name="Unknown",
                  sector="Misc", country="GB", currency="GBP")
    db.add(stock); db.commit()

    frame = _make_pence_frame()

    with patch.object(ohlcv_service, "_get_yfinance_native_currency", return_value=None):
        ins, _ = ohlcv_service._upsert_one_stock(db, stock, frame)
        db.commit()

    assert ins == 0
    bar = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).first()
    assert bar is None  # nothing written — no pence/pounds gamble
