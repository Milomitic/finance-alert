"""Tests for stock_detail_service.

The Tier 2 (per-watchlist override) layer was removed in May 2026 —
the tier-2 test cases that lived here are gone. `source` on
`EffectiveRule` is always "tier1" now.
"""
from datetime import date, timedelta

from app.models import OhlcvDaily, Rule, Stock
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
    assert any(p.value is not None for p in d.sma50)
    assert any(p.value is not None for p in d.rsi14)


def test_get_detail_range_filter_1m(db):
    """v2 timeframe semantics: '1m' now means monthly bars (resampled
    from daily) at full history, NOT a 30-day slice."""
    s = _seed_stock_full(db, n_bars=250)
    d = stock_detail_service.get_detail(db, s.ticker, range_key="1m")
    assert d is not None
    assert 8 <= len(d.ohlcv) <= 15


def test_resolve_effective_rules_returns_globals(db):
    s = _seed_stock_full(db, n_bars=10)
    db.add(Rule(kind="rsi_oversold", params='{"threshold":30}', enabled=True))
    db.add(Rule(kind="death_cross", params='{}', enabled=True))
    db.commit()

    rules = stock_detail_service.resolve_effective_rules(db, s.id)
    assert len(rules) == 2
    kinds = {r.kind: r for r in rules}
    assert kinds["rsi_oversold"].source == "tier1"
    assert kinds["rsi_oversold"].enabled is True
    assert kinds["death_cross"].source == "tier1"
