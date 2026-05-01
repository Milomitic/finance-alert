"""Tests for stats_service aggregation queries."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Alert, Rule, Stock
from app.services.stats_service import KpiSummary, get_kpi_summary


def _seed_baseline(db: Session) -> tuple[Stock, Rule]:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.")
    db.add(stock)
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(stock)
    db.refresh(rule)
    return stock, rule


def _make_alert(
    db: Session,
    stock: Stock,
    rule: Rule,
    *,
    age_hours: float = 0.0,
    archived: bool = False,
) -> Alert:
    a = Alert(
        rule_id=rule.id,
        stock_id=stock.id,
        trigger_price=100.0,
        snapshot="{}",
    )
    a.triggered_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    if archived:
        a.archived_at = datetime.now(timezone.utc)
    db.add(a)
    db.commit()
    return a


def test_kpi_alerts_24h_counts_only_recent_unarchived(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)      # in 24h
    _make_alert(db, stock, rule, age_hours=12)     # in 24h
    _make_alert(db, stock, rule, age_hours=30)     # outside 24h
    _make_alert(db, stock, rule, age_hours=2, archived=True)  # archived → excluded
    summary = get_kpi_summary(db)
    assert isinstance(summary, KpiSummary)
    assert summary.alerts_last_24h == 2


def test_kpi_alerts_prev_24h_window(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)      # in current 24h
    _make_alert(db, stock, rule, age_hours=30)     # in [24h, 48h)
    _make_alert(db, stock, rule, age_hours=40)     # in [24h, 48h)
    _make_alert(db, stock, rule, age_hours=72)     # outside
    summary = get_kpi_summary(db)
    assert summary.alerts_last_24h == 1
    assert summary.alerts_prev_24h == 2


def test_kpi_unread_excludes_archived_and_read(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)
    a_read = _make_alert(db, stock, rule, age_hours=2)
    a_read.read_at = datetime.now(timezone.utc)
    db.commit()
    _make_alert(db, stock, rule, age_hours=2, archived=True)
    summary = get_kpi_summary(db)
    assert summary.alerts_unread == 1


def test_kpi_stocks_and_indices_counts(db: Session) -> None:
    from app.models import Index
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple"))
    db.add(Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft"))
    db.add(Index(code="SP500", name="S&P 500", country="US"))
    db.add(Index(code="NDX", name="Nasdaq-100", country="US"))
    db.add(Index(code="DJI", name="DJIA", country="US"))
    db.commit()
    summary = get_kpi_summary(db)
    assert summary.stocks_monitored == 2
    assert summary.indices_count == 3
