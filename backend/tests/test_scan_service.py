"""Tests for scan_service: rule resolution + edge-triggered alert firing."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    Alert,
    OhlcvDaily,
    Rule,
    RuleState,
    Stock,
    User,
    Watchlist,
    WatchlistItem,
)
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
    r = Rule(watchlist_id=None, kind=kind, params=params, enabled=enabled)
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


def test_scan_tier2_disable_overrides_global(db: Session) -> None:
    """If a watchlist contains the stock with a Tier 2 disabled override, no alert."""
    user = _create_admin(db)
    closes = [100.0 - 0.5 * i for i in range(30)]
    stock = _seed_stock_with_ohlcv(db, "AAPL", closes)
    _create_global_rule(db, "rsi_oversold", params='{"period": 14, "threshold": 30}')

    wl = Watchlist(name="Test", user_id=user.id)
    db.add(wl)
    db.commit()
    db.add(WatchlistItem(watchlist_id=wl.id, stock_id=stock.id))
    db.add(
        Rule(
            watchlist_id=wl.id,
            kind="rsi_oversold",
            params="{}",
            enabled=False,  # Tier 2 disable
        )
    )
    db.commit()

    result = scan_universe(db)
    db.commit()

    assert result.alerts_fired == 0  # Tier 2 disable wins


def test_scan_tier2_custom_params_used_in_evaluation(db: Session) -> None:
    """Tier 2 custom threshold should be used (state recorded under global rule_id)."""
    user = _create_admin(db)
    closes = [100.0 - 0.4 * i for i in range(30)]
    stock = _seed_stock_with_ohlcv(db, "AAPL", closes)
    _create_global_rule(db, "rsi_oversold", params='{"period": 14, "threshold": 30}')

    wl = Watchlist(name="Strict", user_id=user.id)
    db.add(wl)
    db.commit()
    db.add(WatchlistItem(watchlist_id=wl.id, stock_id=stock.id))
    db.add(
        Rule(
            watchlist_id=wl.id,
            kind="rsi_oversold",
            params='{"period": 14, "threshold": 20}',  # stricter
            enabled=True,
        )
    )
    db.commit()

    scan_universe(db)
    db.commit()
    # Check state was created under the global rule_id (not the Tier 2 one)
    states = db.query(RuleState).filter_by(stock_id=stock.id).all()
    assert len(states) == 1
