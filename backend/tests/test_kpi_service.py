"""Tests for KPI capture (append-only time series)."""
import json
from datetime import date

from app.models import Alert, KpiSnapshot, Stock
from app.services import kpi_service


def _seed(db, ticker, name, conf, tone, horizon):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    db.add(Alert(
        stock_id=s.id, trigger_price=10, signal_date=date.today(), signal_name=name,
        snapshot=json.dumps({"tone": tone, "confidence": conf, "chain": [], "horizon": horizon}),
    ))
    db.commit()


def test_active_population_buckets(db):
    _seed(db, "AAA", "trend_pullback", 92, "bull", "long")
    _seed(db, "BBB", "candle_reversal", 65, "bear", "short")
    pop = kpi_service._active_signal_population(db)
    assert pop["total"] == 2
    assert pop["by_tone"] == {"bull": 1, "bear": 1}
    assert pop["by_horizon"] == {"long": 1, "short": 1}
    assert pop["by_confidence"] == {"90-100": 1, "60-69": 1}
    assert pop["by_detector"] == {"trend_pullback": 1, "candle_reversal": 1}


def test_daily_rollup_writes_and_reads_back(db):
    _seed(db, "CCC", "trend_pullback", 90, "bull", "long")
    kpi_service.record_daily_rollup(db, days=365, window=20)
    rows = kpi_service.recent(db, kind="daily_rollup", days=1)
    assert len(rows) == 1
    m = rows[0]["metrics"]
    assert "calibration" in m and "confluence" in m and "signals" in m
    assert m["signals"]["total"] == 1


def test_recent_filters_by_kind(db):
    db.add(KpiSnapshot(kind="scan", metrics=json.dumps({"x": 1})))
    db.add(KpiSnapshot(kind="daily_rollup", metrics=json.dumps({"y": 2})))
    db.commit()
    assert len(kpi_service.recent(db, kind="scan", days=1)) == 1
    assert len(kpi_service.recent(db, kind="daily_rollup", days=1)) == 1
