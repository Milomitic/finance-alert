"""Tests for stock_detail_service.

The rule engine has been fully removed. The `resolve_effective_rules`
function is a backward-compat stub that always returns [].
"""
from datetime import date, timedelta

from app.models import OhlcvDaily, Stock
from app.services import stock_detail_service


def _seed_stock_full(db, ticker: str = "AAPL", n_bars: int = 250) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
              sector="Technology", country="US", currency="USD")
    db.add(s); db.commit()
    today = date(2026, 5, 2)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        c = 100.0 + 0.1 * i
        db.add(OhlcvDaily(
            stock_id=s.id, date=d,
            open=c - 0.5, high=c + 0.5, low=c - 1.0, close=c, volume=1_000_000,
        ))
    db.commit()
    return s


def test_get_detail_returns_none_for_missing_ticker(db):
    assert stock_detail_service.get_detail(db, "MISSING") is None


def test_get_detail_full_payload(db):
    s = _seed_stock_full(db, n_bars=250)
    d = stock_detail_service.get_detail(db, s.ticker, range_key="1y")
    assert d is not None
    assert d.stock.ticker == "AAPL"
    assert len(d.ohlcv) > 0
    assert d.kpis.last_close is not None
    assert d.kpis.high_52w is not None
    assert any(p.value is not None for p in d.ema50)
    assert any(p.value is not None for p in d.rsi14)


def test_get_detail_range_filter_1m(db):
    """v2 timeframe semantics: '1m' now means monthly bars (resampled
    from daily) at full history, NOT a 30-day slice."""
    s = _seed_stock_full(db, n_bars=250)
    d = stock_detail_service.get_detail(db, s.ticker, range_key="1m")
    assert d is not None
    assert 8 <= len(d.ohlcv) <= 15


def test_resolve_effective_rules_returns_empty(db):
    """Rules are being removed — function returns [] as backward-compat stub."""
    s = _seed_stock_full(db, n_bars=10)
    rules = stock_detail_service.resolve_effective_rules(db, s.id)
    assert rules == []


def test_alerts_history_uses_signal_kind(db):
    """alerts_history derives kind from signal_name, not rule join."""
    from app.models import Alert
    s = _seed_stock_full(db, n_bars=10)
    db.add(Alert(
        signal_name="rsi_oversold",
        stock_id=s.id,
        trigger_price=100.0,
        snapshot="{}",
    ))
    db.commit()
    d = stock_detail_service.get_detail(db, s.ticker, range_key="1y")
    assert d is not None
    assert len(d.alerts_history) == 1
    alert_obj, kind = d.alerts_history[0]
    assert kind == "signal:rsi_oversold"
