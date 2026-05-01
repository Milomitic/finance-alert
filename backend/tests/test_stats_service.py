"""Tests for stats_service aggregation queries."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Alert, Rule, Stock
from app.services.stats_service import (
    AlertsByDayPoint,
    KpiSummary,
    TopStock,
    get_alerts_by_day,
    get_kpi_summary,
    get_top_stocks,
)


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


def test_alerts_by_day_groups_by_date_and_kind(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    rule2 = Rule(watchlist_id=None, kind="golden_cross", params="{}", enabled=True)
    db.add(rule2)
    db.commit()
    db.refresh(rule2)
    # Today: 2 oversold + 1 cross
    _make_alert(db, stock, rule, age_hours=2)
    _make_alert(db, stock, rule, age_hours=3)
    _make_alert(db, stock, rule2, age_hours=4)
    # Yesterday: 1 oversold
    _make_alert(db, stock, rule, age_hours=26)
    points = get_alerts_by_day(db, days=30)
    assert all(isinstance(p, AlertsByDayPoint) for p in points)
    today_iso = (date.today())
    yesterday_iso = today_iso - timedelta(days=1)
    by_date = {p.date: p for p in points}
    assert by_date[today_iso].count == 3
    assert by_date[today_iso].by_kind == {"rsi_oversold": 2, "golden_cross": 1}
    assert by_date[yesterday_iso].count == 1
    assert by_date[yesterday_iso].by_kind == {"rsi_oversold": 1}


def test_alerts_by_day_includes_zero_days_in_range(db: Session) -> None:
    """Days with no alerts must still be present (count=0) so the chart is continuous."""
    _seed_baseline(db)  # no alerts
    points = get_alerts_by_day(db, days=7)
    assert len(points) == 7
    assert all(p.count == 0 for p in points)
    assert all(p.by_kind == {} for p in points)


def test_alerts_by_day_excludes_archived(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)
    _make_alert(db, stock, rule, age_hours=2, archived=True)
    points = get_alerts_by_day(db, days=1)
    today_pt = next(p for p in points if p.date == date.today())
    assert today_pt.count == 1


def test_top_stocks_orders_by_count_desc_limit_10(db: Session) -> None:
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    stocks = []
    for i in range(12):
        s = Stock(ticker=f"T{i:02d}", exchange="X", name=f"Stock {i}")
        db.add(s)
        db.commit()
        db.refresh(s)
        stocks.append(s)
        # Stock with index i gets (i+1) alerts to enforce ordering
        for _ in range(i + 1):
            _make_alert(db, s, rule, age_hours=1)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 10
    # Highest count first; ties broken by ticker ASC (no ties here, but verify ordering)
    assert top[0].ticker == "T11" and top[0].alert_count == 12
    assert top[-1].ticker == "T02" and top[-1].alert_count == 3


def test_top_stocks_top_kind_is_most_frequent(db: Session) -> None:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    rule_oversold = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    rule_cross = Rule(watchlist_id=None, kind="golden_cross", params="{}", enabled=True)
    db.add(rule_oversold)
    db.add(rule_cross)
    db.commit()
    db.refresh(stock)
    db.refresh(rule_oversold)
    db.refresh(rule_cross)
    _make_alert(db, stock, rule_oversold, age_hours=2)
    _make_alert(db, stock, rule_oversold, age_hours=3)
    _make_alert(db, stock, rule_cross, age_hours=4)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 1
    assert top[0].top_kind == "rsi_oversold"


def test_top_stocks_excludes_archived(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)
    _make_alert(db, stock, rule, age_hours=2, archived=True)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 1 and top[0].alert_count == 1
