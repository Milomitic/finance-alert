"""Tests for spotlight_service + stats_service.get_top_alerted_stock_7d."""
import json
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, MarketSnapshot, OhlcvDaily, Stock
from app.services import spotlight_service, stats_service


def _seed_stock(db, ticker: str, n_bars: int = 30) -> Stock:
    s = Stock(ticker=ticker, exchange="NMS", name=ticker)
    db.add(s); db.commit()
    today = date(2026, 5, 2)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        c = 100.0 + i
        db.add(OhlcvDaily(stock_id=s.id, date=d,
                          open=c, high=c, low=c, close=c, volume=1_000_000))
    db.commit()
    return s


def test_top_alerted_7d_empty(db):
    assert stats_service.get_top_alerted_stock_7d(db) is None


def test_top_alerted_7d_returns_winner(db):
    s1 = _seed_stock(db, "A")
    s2 = _seed_stock(db, "B")
    now = datetime.now(UTC)
    for _ in range(5):
        db.add(Alert(stock_id=s1.id, trigger_price=100.0,
                     snapshot="{}", triggered_at=now - timedelta(hours=1),
                     signal_name="rsi_oversold"))
    for _ in range(2):
        db.add(Alert(stock_id=s2.id, trigger_price=100.0,
                     snapshot="{}", triggered_at=now - timedelta(hours=1),
                     signal_name="rsi_oversold"))
    db.commit()
    result = stats_service.get_top_alerted_stock_7d(db)
    assert result is not None
    stock, count = result
    assert stock.ticker == "A"
    assert count == 5


def test_build_spotlight_with_snapshot_and_alerts(db):
    _seed_stock(db, "NVDA")
    s2 = _seed_stock(db, "AAPL")
    _seed_stock(db, "PLTR")
    payload = {
        "movers": {
            "gainers": [{"ticker": "NVDA", "change_pct": 4.2, "last_close": 880.0}],
            "volume_spikes": [{"ticker": "PLTR", "vol_ratio": 3.2, "last_close": 28.5}],
            "losers": [], "new_52w_high": [], "new_52w_low": [],
        }
    }
    db.merge(MarketSnapshot(
        id=1, computed_at=datetime.now(UTC),
        stocks_total=3, stocks_with_data=3, payload=json.dumps(payload),
    ))
    db.add(Alert(stock_id=s2.id, trigger_price=170.0,
                 snapshot="{}", triggered_at=datetime.now(UTC) - timedelta(hours=1),
                 signal_name="rsi_oversold"))
    db.commit()

    cards = spotlight_service.build(db)
    types = {c["type"] for c in cards}
    assert "top_gainer" in types
    assert "most_alerted_7d" in types
    assert "vol_spike" in types
    by_type = {c["type"]: c for c in cards}
    assert by_type["top_gainer"]["ticker"] == "NVDA"
    assert by_type["most_alerted_7d"]["ticker"] == "AAPL"
    assert by_type["vol_spike"]["ticker"] == "PLTR"
    assert len(by_type["top_gainer"]["sparkline"]) > 0


def test_build_spotlight_no_snapshot(db):
    cards = spotlight_service.build(db)
    assert cards == []
