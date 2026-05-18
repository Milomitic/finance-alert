"""Tests for OHLCV fetch + upsert service."""
from unittest.mock import patch

import pandas as pd
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services.ohlcv_service import FetchResult, fetch_and_upsert


def _seed_stock(db: Session, ticker: str = "AAPL") -> Stock:
    stock = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Co")
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


def _fake_yf_response(tickers: list[str]) -> pd.DataFrame:
    """Mimic yfinance.download(tickers=[...], group_by='ticker') multi-index DataFrame."""
    dates = pd.date_range("2026-01-01", periods=5, freq="D")
    frames = {}
    for t in tickers:
        frames[t] = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "High": [101.0, 102.0, 103.0, 104.0, 105.0],
                "Low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "Close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "Volume": [1_000_000] * 5,
            },
            index=dates,
        )
    return pd.concat(frames, axis=1)


def test_fetch_inserts_5_rows_for_one_stock(db: Session) -> None:
    stock = _seed_stock(db)
    with patch(
        "app.services.ohlcv_service._yf_download",
        return_value=_fake_yf_response(["AAPL"]),
    ):
        result = fetch_and_upsert(db, [stock], period="1mo")
    db.commit()
    assert isinstance(result, FetchResult)
    assert result.rows_inserted == 5
    assert result.stocks_succeeded == 1
    assert result.stocks_failed == 0
    rows = db.query(OhlcvDaily).filter_by(stock_id=stock.id).all()
    assert len(rows) == 5
    assert rows[0].close > 0


def test_fetch_upsert_is_idempotent(db: Session) -> None:
    stock = _seed_stock(db)
    with patch(
        "app.services.ohlcv_service._yf_download",
        return_value=_fake_yf_response(["AAPL"]),
    ):
        fetch_and_upsert(db, [stock], period="1mo")
        fetch_and_upsert(db, [stock], period="1mo")  # second call should not duplicate
    db.commit()
    rows = db.query(OhlcvDaily).filter_by(stock_id=stock.id).all()
    assert len(rows) == 5  # still 5, not 10


def _capture_loguru():
    """Context-free loguru capture: returns (records, remove_fn).

    pytest's caplog doesn't see loguru sinks, so we attach a temporary
    one. Each captured record is the loguru dict; we only need .level
    and .message for these assertions."""
    from loguru import logger

    records: list[tuple[str, str]] = []
    sink_id = logger.add(
        lambda m: records.append(
            (m.record["level"].name, m.record["message"])
        ),
        level="DEBUG",
        format="{message}",
    )
    return records, lambda: logger.remove(sink_id)


def _yf_with_unsettled_last_bar(ticker: str) -> pd.DataFrame:
    """5 clean bars + a 6th LATEST bar where Close is NaN but O/H/L are
    valid — yfinance's unsettled-last-bar artifact."""
    import numpy as np
    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "High": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "Low": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5, np.nan],  # last NaN
            "Volume": [1_000_000] * 6,
        },
        index=dates,
    )
    return pd.concat({ticker: frame}, axis=1)


def _yf_with_corrupt_history_bar(ticker: str) -> pd.DataFrame:
    """A NaN close in the MIDDLE of the history (not the last bar) —
    genuine corruption that must stay a WARNING."""
    import numpy as np
    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "High": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "Low": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0],
            "Close": [100.5, 101.5, np.nan, 103.5, 104.5, 105.5],  # mid NaN
            "Volume": [1_000_000] * 6,
        },
        index=dates,
    )
    return pd.concat({ticker: frame}, axis=1)


def test_unsettled_last_bar_skipped_at_debug_not_warning(db: Session) -> None:
    """The latest bar with only Close=NaN is yfinance's normal
    unsettled-bar artifact: skipped (a NaN close would wreck the chart)
    but logged at DEBUG so it doesn't flood the WARNING-level
    platform-health stream. The 5 good bars still insert."""
    stock = _seed_stock(db, "AAPL")
    records, remove = _capture_loguru()
    try:
        with patch(
            "app.services.ohlcv_service._yf_download",
            return_value=_yf_with_unsettled_last_bar("AAPL"),
        ):
            result = fetch_and_upsert(db, [stock], period="1mo")
        db.commit()
    finally:
        remove()

    assert result.rows_inserted == 5  # 6th (NaN close) skipped
    skip_lines = [
        (lvl, msg) for (lvl, msg) in records
        if "skip corrupt bar AAPL" in msg
    ]
    assert len(skip_lines) == 1
    lvl, msg = skip_lines[0]
    assert lvl == "DEBUG", f"expected DEBUG for unsettled last bar, got {lvl}"
    assert "close not settled" in msg


def test_corrupt_history_bar_stays_warning(db: Session) -> None:
    """A NaN close in the MIDDLE of the series is genuine corruption —
    actionable, must remain a WARNING (not downgraded to DEBUG)."""
    stock = _seed_stock(db, "AAPL")
    records, remove = _capture_loguru()
    try:
        with patch(
            "app.services.ohlcv_service._yf_download",
            return_value=_yf_with_corrupt_history_bar("AAPL"),
        ):
            result = fetch_and_upsert(db, [stock], period="1mo")
        db.commit()
    finally:
        remove()

    assert result.rows_inserted == 5  # the mid NaN bar skipped
    skip_lines = [
        (lvl, msg) for (lvl, msg) in records
        if "skip corrupt bar AAPL" in msg
    ]
    assert len(skip_lines) == 1
    lvl, _msg = skip_lines[0]
    assert lvl == "WARNING", f"mid-history corruption must stay WARNING, got {lvl}"


def test_fetch_handles_per_stock_failure(db: Session) -> None:
    aapl = _seed_stock(db, "AAPL")
    msft = _seed_stock(db, "MSFT")

    # Simulate MSFT having no data (KeyError-like behavior)
    def selective(_tickers, **_kwargs):
        return _fake_yf_response(["AAPL"])  # MSFT missing from response

    with patch("app.services.ohlcv_service._yf_download", side_effect=selective):
        result = fetch_and_upsert(db, [aapl, msft], period="1mo")
    db.commit()
    assert result.stocks_succeeded == 1
    assert result.stocks_failed == 1
    # AAPL got rows, MSFT did not
    assert db.query(OhlcvDaily).filter_by(stock_id=aapl.id).count() == 5
    assert db.query(OhlcvDaily).filter_by(stock_id=msft.id).count() == 0
