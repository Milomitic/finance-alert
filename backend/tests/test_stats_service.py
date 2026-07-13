"""Tests for stats_service aggregation queries."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Alert, Stock
from app.services.stats_service import (
    AlertsByDayPoint,
    KpiSummary,
    get_alerts_by_day,
    get_kpi_summary,
    get_top_stocks,
)


def _seed_baseline(db: Session) -> Stock:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.")
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


def _make_alert(
    db: Session,
    stock: Stock,
    *,
    signal_name: str = "rsi_oversold",
    age_hours: float = 0.0,
    archived: bool = False,
) -> Alert:
    a = Alert(
        stock_id=stock.id,
        trigger_price=100.0,
        snapshot="{}",
        signal_name=signal_name,
    )
    a.triggered_at = datetime.now(UTC) - timedelta(hours=age_hours)
    if archived:
        a.archived_at = datetime.now(UTC)
    db.add(a)
    db.commit()
    return a


def test_kpi_alerts_24h_counts_only_recent_unarchived(db: Session) -> None:
    stock = _seed_baseline(db)
    _make_alert(db, stock, age_hours=2)      # in 24h
    _make_alert(db, stock, age_hours=12)     # in 24h
    _make_alert(db, stock, age_hours=30)     # outside 24h
    _make_alert(db, stock, age_hours=2, archived=True)  # archived → excluded
    summary = get_kpi_summary(db)
    assert isinstance(summary, KpiSummary)
    assert summary.alerts_last_24h == 2


def test_kpi_alerts_prev_24h_window(db: Session) -> None:
    stock = _seed_baseline(db)
    _make_alert(db, stock, age_hours=2)      # in current 24h
    _make_alert(db, stock, age_hours=30)     # in [24h, 48h)
    _make_alert(db, stock, age_hours=40)     # in [24h, 48h)
    _make_alert(db, stock, age_hours=72)     # outside
    summary = get_kpi_summary(db)
    assert summary.alerts_last_24h == 1
    assert summary.alerts_prev_24h == 2


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
    """Tests bucketing of alerts by UTC date.

    To stay deterministic at any wall-clock time (including the few
    minutes around UTC midnight where 2-4h-ago alerts straddle the
    day boundary), we DERIVE the expected target date for each alert
    from a reference UTC timestamp captured before seeding rather
    than hardcoding "today + yesterday". This way the assertion
    always matches whichever day the seeded triggered_at actually
    lands on, regardless of clock position.
    """
    stock = _seed_baseline(db)
    # Capture the reference UTC moment first; _make_alert uses
    # datetime.now(UTC) internally so the dates derived here will
    # match (within the few-millisecond gap between calls).
    ref = datetime.now(UTC)

    def _date_at(hours: float) -> "date":
        return (ref - timedelta(hours=hours)).date()

    _make_alert(db, stock, signal_name="rsi_oversold", age_hours=2)
    _make_alert(db, stock, signal_name="rsi_oversold", age_hours=3)
    _make_alert(db, stock, signal_name="golden_cross", age_hours=4)
    _make_alert(db, stock, signal_name="rsi_oversold", age_hours=26)

    points = get_alerts_by_day(db, days=30)
    assert all(isinstance(p, AlertsByDayPoint) for p in points)
    by_date = {p.date: p for p in points}

    # Aggregate expected counts by deriving each alert's date.
    expected: dict = {}
    for hours, kind in [(2, "signal:rsi_oversold"), (3, "signal:rsi_oversold"),
                        (4, "signal:golden_cross"), (26, "signal:rsi_oversold")]:
        d = _date_at(hours)
        bucket = expected.setdefault(d, {"count": 0, "by_kind": {}})
        bucket["count"] += 1
        bucket["by_kind"][kind] = bucket["by_kind"].get(kind, 0) + 1

    for d, exp in expected.items():
        assert by_date[d].count == exp["count"], f"day {d}: count"
        assert by_date[d].by_kind == exp["by_kind"], f"day {d}: by_kind"


def test_alerts_by_day_includes_zero_days_in_range(db: Session) -> None:
    """Days with no alerts must still be present (count=0) so the chart is continuous."""
    _seed_baseline(db)  # no alerts
    points = get_alerts_by_day(db, days=7)
    assert len(points) == 7
    assert all(p.count == 0 for p in points)
    assert all(p.by_kind == {} for p in points)


def test_alerts_by_day_excludes_archived(db: Session) -> None:
    """Same time-derivation trick as
    test_alerts_by_day_groups_by_date_and_kind — captures the UTC
    reference moment before seeding so the expected date matches
    whichever UTC day the 2h-ago alert actually lands on. Robust
    even when running at UTC 00:00-02:00."""
    stock = _seed_baseline(db)
    ref = datetime.now(UTC)
    target_date = (ref - timedelta(hours=2)).date()

    _make_alert(db, stock, age_hours=2)
    _make_alert(db, stock, age_hours=2, archived=True)

    # days=2 covers the case where the 2h-ago alert lands on UTC
    # yesterday (clock just rolled past midnight). days=1 would only
    # return today's point and miss the alert.
    points = get_alerts_by_day(db, days=2)
    target_pt = next(p for p in points if p.date == target_date)
    assert target_pt.count == 1


def test_top_stocks_orders_by_count_desc_limit_10(db: Session) -> None:
    stocks = []
    for i in range(12):
        s = Stock(ticker=f"T{i:02d}", exchange="X", name=f"Stock {i}")
        db.add(s)
        db.commit()
        db.refresh(s)
        stocks.append(s)
        # Stock with index i gets (i+1) alerts to enforce ordering
        for _ in range(i + 1):
            _make_alert(db, s, age_hours=1)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 10
    # Highest count first; ties broken by ticker ASC (no ties here, but verify ordering)
    assert top[0].ticker == "T11" and top[0].alert_count == 12
    assert top[-1].ticker == "T02" and top[-1].alert_count == 3


def test_top_stocks_top_kind_is_most_frequent(db: Session) -> None:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    db.commit()
    db.refresh(stock)
    _make_alert(db, stock, signal_name="rsi_oversold", age_hours=2)
    _make_alert(db, stock, signal_name="rsi_oversold", age_hours=3)
    _make_alert(db, stock, signal_name="golden_cross", age_hours=4)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 1
    assert top[0].top_kind == "signal:rsi_oversold"


def test_top_stocks_excludes_archived(db: Session) -> None:
    stock = _seed_baseline(db)
    _make_alert(db, stock, age_hours=2)
    _make_alert(db, stock, age_hours=2, archived=True)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 1 and top[0].alert_count == 1


import pytest

from app.services.stats_service import SystemStatus, get_system_status


def test_system_status_telegram_configured_when_token_and_chat_set(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    status = get_system_status(db)
    assert isinstance(status, SystemStatus)
    assert status.telegram_configured is True


def test_system_status_telegram_not_configured_when_blank(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    status = get_system_status(db)
    assert status.telegram_configured is False


def test_system_status_includes_scheduler_next_runs(db: Session) -> None:
    """next_run fields are pulled from the live APScheduler. With the scheduler
    not started in this test, the fields are None — that's the contract."""
    status = get_system_status(db)
    assert isinstance(status.scheduler_running, bool)
    assert status.scan_alerts_next_run is None or hasattr(status.scan_alerts_next_run, "isoformat")
