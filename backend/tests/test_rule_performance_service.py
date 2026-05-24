"""Tests for rule_performance_service after signal-name refactor.

Verifies that compute_performance groups efficacy rows by
"signal:<name>" (not by Rule.kind) and that the forward-return math
is preserved.
"""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import Alert, OhlcvDaily, Stock
from app.services.rule_performance_service import compute_performance


def _make_stock(db, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"Test {ticker}", country="US")
    db.add(s)
    db.flush()
    return s


def _add_bars(db, stock_id: int, start_date: date, closes: list[float]) -> None:
    """Add OHLCV rows for `stock_id` starting at `start_date`, one per day."""
    for i, close in enumerate(closes):
        d = start_date + timedelta(days=i)
        db.add(OhlcvDaily(
            stock_id=stock_id, date=d,
            open=close, high=close + 1, low=close - 1, close=close,
            volume=1_000,
        ))


def _make_alert(db, stock_id: int, signal_name: str, signal_date: date,
                triggered_at: datetime | None = None, tone: str | None = None) -> Alert:
    if triggered_at is None:
        triggered_at = datetime.now(UTC)
    snapshot = f'{{"tone": "{tone}"}}' if tone else "{}"
    a = Alert(
        stock_id=stock_id,
        trigger_price=100.0,
        signal_date=signal_date,
        triggered_at=triggered_at,
        snapshot=snapshot,
        signal_name=signal_name,
    )
    db.add(a)
    return a


# ---------------------------------------------------------------------------
# Basic grouping by signal_name
# ---------------------------------------------------------------------------

def test_groups_by_signal_name(db):
    """Two different signals → two separate performance rows."""
    s1 = _make_stock(db, "PERF1")
    s2 = _make_stock(db, "PERF2")

    sig_date = date(2026, 1, 2)
    # 25 bars: signal at index 0, 1d/5d/20d forward data available
    _add_bars(db, s1.id, sig_date, [100.0] * 25)
    _add_bars(db, s2.id, sig_date, [200.0] * 25)

    _make_alert(db, s1.id, "rsi_oversold", sig_date)
    _make_alert(db, s2.id, "golden_cross", sig_date)
    db.commit()

    rows = compute_performance(db, days=365)
    kinds = {r.rule_kind for r in rows}

    assert "signal:rsi_oversold" in kinds
    assert "signal:golden_cross" in kinds
    # No "rsi_oversold" or "golden_cross" without the "signal:" prefix
    assert "rsi_oversold" not in kinds
    assert "golden_cross" not in kinds


def test_multiple_alerts_same_signal(db):
    """Multiple alerts with the same signal_name → one row, count aggregated."""
    s = _make_stock(db, "PERF3")
    sig_date = date(2026, 1, 2)
    _add_bars(db, s.id, sig_date, [100.0] * 25)

    for _ in range(3):
        _make_alert(db, s.id, "volume_breakout", sig_date)
    db.commit()

    rows = compute_performance(db, days=365)
    assert len(rows) == 1
    assert rows[0].rule_kind == "signal:volume_breakout"
    assert rows[0].total_alerts == 3


# ---------------------------------------------------------------------------
# Forward-return math (unchanged behaviour)
# ---------------------------------------------------------------------------

def test_bullish_signal_positive_return_counted_as_hit(db):
    """rsi_oversold is bullish; a rising price → hit_rate > 0."""
    s = _make_stock(db, "PERF4")
    sig_date = date(2026, 1, 2)
    # Price rises: signal close 100, day-1 close 110 → +10%
    closes = [100.0] + [110.0] * 24
    _add_bars(db, s.id, sig_date, closes)

    _make_alert(db, s.id, "rsi_oversold", sig_date, tone="bull")
    db.commit()

    rows = compute_performance(db, days=365, windows=(1,))
    assert len(rows) == 1
    row = rows[0]
    assert row.rule_kind == "signal:rsi_oversold"
    assert row.tone == "bull"
    s1 = row.stats[1]
    assert s1.count == 1
    assert s1.mean_pct is not None and s1.mean_pct > 0
    assert s1.hit_rate == 1.0


def test_bearish_signal_negative_return_counted_as_hit(db):
    """rsi_overbought is bearish; a falling price → hit_rate = 1."""
    s = _make_stock(db, "PERF5")
    sig_date = date(2026, 1, 2)
    closes = [100.0] + [90.0] * 24
    _add_bars(db, s.id, sig_date, closes)

    _make_alert(db, s.id, "rsi_overbought", sig_date, tone="bear")
    db.commit()

    rows = compute_performance(db, days=365, windows=(1,))
    assert len(rows) == 1
    row = rows[0]
    assert row.tone == "bear"
    assert row.stats[1].hit_rate == 1.0


def test_neutral_signal_no_hit_rate(db):
    """volume_spike is neutral; hit_rate must be None."""
    s = _make_stock(db, "PERF6")
    sig_date = date(2026, 1, 2)
    _add_bars(db, s.id, sig_date, [100.0] * 25)

    _make_alert(db, s.id, "volume_spike", sig_date)
    db.commit()

    rows = compute_performance(db, days=365, windows=(1,))
    assert rows[0].stats[1].hit_rate is None


# ---------------------------------------------------------------------------
# Filters: archived alerts excluded; old alerts excluded; None signal_name skipped
# ---------------------------------------------------------------------------

def test_archived_alerts_excluded(db):
    s = _make_stock(db, "PERF7")
    sig_date = date(2026, 1, 2)
    _add_bars(db, s.id, sig_date, [100.0] * 25)

    a = _make_alert(db, s.id, "rsi_oversold", sig_date)
    a.archived_at = datetime.now(UTC)
    db.commit()

    rows = compute_performance(db, days=365)
    assert rows == []


def test_old_alerts_excluded(db):
    """Alert older than `days` cutoff is not included."""
    s = _make_stock(db, "PERF8")
    sig_date = date(2024, 1, 2)
    _add_bars(db, s.id, sig_date, [100.0] * 25)

    old_ts = datetime.now(UTC) - timedelta(days=200)
    _make_alert(db, s.id, "rsi_oversold", sig_date, triggered_at=old_ts)
    db.commit()

    rows = compute_performance(db, days=90)
    assert rows == []


def test_none_signal_name_skipped(db):
    """Alerts with signal_name=None (not produced by signal engine) are skipped."""
    s = _make_stock(db, "PERF9")
    sig_date = date(2026, 1, 2)
    _add_bars(db, s.id, sig_date, [100.0] * 25)

    # Simulate an alert without signal_name — filter at DB level
    a = Alert(
        stock_id=s.id,
        trigger_price=100.0,
        signal_date=sig_date,
        triggered_at=datetime.now(UTC),
        snapshot="{}",
        signal_name=None,   # explicitly None
    )
    db.add(a)
    db.commit()

    rows = compute_performance(db, days=365)
    assert rows == []


# ---------------------------------------------------------------------------
# Sorted by total_alerts descending
# ---------------------------------------------------------------------------

def test_sorted_by_total_alerts_desc(db):
    s = _make_stock(db, "PERFA")
    sig_date = date(2026, 1, 2)
    _add_bars(db, s.id, sig_date, [100.0] * 25)

    # 1 rsi_oversold, 3 golden_cross
    _make_alert(db, s.id, "rsi_oversold", sig_date)
    for _ in range(3):
        _make_alert(db, s.id, "golden_cross", sig_date)
    db.commit()

    rows = compute_performance(db, days=365)
    assert rows[0].total_alerts >= rows[1].total_alerts
    assert rows[0].rule_kind == "signal:golden_cross"
