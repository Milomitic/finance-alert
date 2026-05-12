"""Tests for scan_service: rule resolution + edge-triggered alert firing.

The Tier 2 (per-watchlist override) layer was removed in May 2026.
The two tier2-specific scenarios that lived here are gone.
"""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, Rule, RuleState, Stock, User
from app.services.scan_service import ScanResult, scan_universe


def _create_admin(db: Session) -> User:
    u = User(username="admin", password_hash="x")
    db.add(u)
    db.commit()
    return u


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


def _create_global_rule(db: Session, kind: str, params: str = "{}", enabled: bool = True) -> Rule:
    r = Rule(kind=kind, params=params, enabled=enabled)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_scan_fires_alert_on_first_true_evaluation(db: Session) -> None:
    """Stock with steadily declining prices should trigger RSI oversold."""
    _create_admin(db)
    closes = [100.0 - 0.5 * i for i in range(30)]
    stock = _seed_stock_with_ohlcv(db, "AAPL", closes)
    _create_global_rule(db, "rsi_oversold", params='{"period": 14, "threshold": 30}')

    result = scan_universe(db)
    db.commit()

    assert isinstance(result, ScanResult)
    assert result.alerts_fired == 1
    assert db.query(Alert).count() == 1
    alert = db.query(Alert).one()
    assert alert.stock_id == stock.id


def test_scan_does_not_refire_when_state_already_true(db: Session) -> None:
    """If RuleState says condition was True last time and is still True, no new alert."""
    _create_admin(db)
    closes = [100.0 - 0.5 * i for i in range(30)]
    stock = _seed_stock_with_ohlcv(db, "AAPL", closes)
    rule = _create_global_rule(db, "rsi_oversold", params='{"period": 14, "threshold": 30}')

    # Pre-seed the state as "already true"
    db.add(
        RuleState(
            rule_id=rule.id,
            stock_id=stock.id,
            last_evaluation=True,
            last_evaluated_at=datetime.now(UTC),
        )
    )
    db.commit()

    result = scan_universe(db)
    db.commit()

    assert result.alerts_fired == 0
    assert db.query(Alert).count() == 0


def test_scan_skips_stocks_without_ohlcv(db: Session) -> None:
    _create_admin(db)
    _seed_stock_with_ohlcv(db, "EMPTY", [])  # no closes -> no rows
    _create_global_rule(db, "rsi_oversold", params='{"period": 14, "threshold": 30}')

    result = scan_universe(db)
    db.commit()
    assert result.alerts_fired == 0
    assert result.stocks_skipped >= 1


def test_scan_respects_disabled_global_rule(db: Session) -> None:
    _create_admin(db)
    closes = [100.0 - 0.5 * i for i in range(30)]
    _seed_stock_with_ohlcv(db, "AAPL", closes)
    _create_global_rule(db, "rsi_oversold", params='{"period": 14, "threshold": 30}', enabled=False)

    result = scan_universe(db)
    db.commit()
    assert result.alerts_fired == 0


def test_scan_uses_expression_when_present(db) -> None:
    """When Rule.expression is set, scan_service uses the composite evaluator."""
    import json
    from datetime import date, timedelta

    from app.models import OhlcvDaily, Rule, Stock
    from app.services.scan_service import scan_universe

    s = Stock(ticker="EXPRTEST.MI", name="Test", exchange="BIT", currency="EUR")
    db.add(s)
    db.commit()
    db.refresh(s)
    base = date(2025, 1, 1)
    closes = [100.0 - i * 0.5 for i in range(40)]
    for i, c in enumerate(closes):
        db.add(OhlcvDaily(stock_id=s.id, date=base + timedelta(days=i),
                          open=c, high=c, low=c, close=c, volume=1000))
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "volume_spike", "params": {"window": 5, "threshold": 0.0}},
        ],
    }
    rule = Rule(
        kind="composite",
        params="{}",
        expression=json.dumps(expr),
        enabled=True,
    )
    db.add(rule)
    db.commit()
    result = scan_universe(db)
    assert result.alerts_fired >= 1
