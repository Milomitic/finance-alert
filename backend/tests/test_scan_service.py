"""Tests for scan_service: signals-only scan.

Rule evaluation was removed from the scan in May 2026; all rule-alert and
RuleState edge-trigger tests have been deleted.  The signal-alert tests live
in test_scan_emits_signal_alerts.py.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, Stock
from app.services.scan_service import ScanResult, scan_universe


def _seed_stock_with_ohlcv(db: Session, ticker: str, closes: list[float]) -> Stock:
    """Create a stock with N daily bars ending on today; closes ascending in time."""
    stock = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Co")
    db.add(stock)
    db.commit()
    db.refresh(stock)
    n = len(closes)
    if n == 0:
        return stock
    base_date = date.today() - timedelta(days=n - 1)
    for i, c in enumerate(closes):
        db.add(
            OhlcvDaily(
                stock_id=stock.id,
                date=base_date + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=1_000_000,
            )
        )
    db.commit()
    return stock


def test_scan_skips_stocks_without_ohlcv(db: Session) -> None:
    """Stocks without OHLCV rows are counted as skipped, not scanned."""
    _seed_stock_with_ohlcv(db, "EMPTY", [])  # no closes -> no rows

    result = scan_universe(db)
    db.commit()
    assert result.alerts_fired == 0
    assert result.stocks_skipped >= 1


def test_scan_returns_scan_result(db: Session) -> None:
    """scan_universe returns a ScanResult even when no stocks are present."""
    result = scan_universe(db)
    assert isinstance(result, ScanResult)


def test_scan_skips_stocks_with_only_one_bar(db: Session) -> None:
    """A stock with a single OHLCV bar is skipped (need >= 2 bars)."""
    _seed_stock_with_ohlcv(db, "ONE", [50.0])

    result = scan_universe(db)
    db.commit()
    assert result.stocks_skipped >= 1
    assert result.stocks_scanned == 0


def test_scan_counts_scanned_stocks(db: Session) -> None:
    """Stocks with sufficient OHLCV are counted in stocks_scanned."""
    closes = [100.0 - 0.5 * i for i in range(30)]
    _seed_stock_with_ohlcv(db, "AAPL", closes)

    result = scan_universe(db)
    db.commit()
    assert result.stocks_scanned >= 1


def test_scan_progress_callback_called(db: Session) -> None:
    """on_progress is called at scan start and end."""
    calls: list[tuple] = []

    def record(done, total, res, ticker):
        calls.append((done, total, ticker))

    scan_universe(db, on_progress=record, progress_every=1)

    assert len(calls) >= 2  # at minimum start + end bookends
    # First call: done=0 (start bookend)
    assert calls[0][0] == 0
    # Last call: done==total
    assert calls[-1][0] == calls[-1][1]


def test_scan_cancel_check_raises(db: Session) -> None:
    """When cancel_check returns True the scan raises ScanCancelled."""
    from app.services.scan_service import ScanCancelled

    closes = [100.0 - 0.5 * i for i in range(30)]
    _seed_stock_with_ohlcv(db, "CANCEL", closes)

    import pytest
    with pytest.raises(ScanCancelled):
        scan_universe(db, cancel_check=lambda: True, progress_every=1)
