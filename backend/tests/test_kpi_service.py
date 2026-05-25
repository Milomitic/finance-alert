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


# --- compute_flags ---------------------------------------------------

def _now_iso():
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


def _healthy_scan():
    return {
        "id": 1, "captured_at": _now_iso(), "scope": None,
        "metrics": {
            "stocks_scanned": 1000, "stocks_skipped": 10, "alerts_fired": 30,
            "data_sources": [{"source": "yfinance", "op": "ohlcv", "success": 990,
                              "failure": 5, "success_rate": 0.99, "health": "ok"}],
        },
    }


def _mature_rollup():
    return {
        "id": 1, "captured_at": _now_iso(), "scope": None,
        "metrics": {"calibration": {"by_confidence": [
            {"label": "60-69", "count": 40}, {"label": "70-79", "count": 30}]}},
    }


def test_compute_flags_healthy():
    flags = kpi_service.compute_flags([_healthy_scan()], [_mature_rollup()])
    assert len(flags) == 1
    assert flags[0]["level"] == "ok" and flags[0]["code"] == "healthy"


def test_compute_flags_no_scans_no_rollup():
    flags = kpi_service.compute_flags([], [])
    codes = {f["code"] for f in flags}
    assert "no_scans" in codes and "no_rollup" in codes


def test_compute_flags_empty_scan_is_error_first():
    scan = _healthy_scan()
    scan["metrics"]["stocks_scanned"] = 0
    flags = kpi_service.compute_flags([scan], [_mature_rollup()])
    assert flags[0]["level"] == "error" and flags[0]["code"] == "scan_empty"


def test_compute_flags_source_down_and_immature_calibration():
    scan = _healthy_scan()
    scan["metrics"]["data_sources"][0].update(health="down", success_rate=0.10)
    rollup = _mature_rollup()
    rollup["metrics"]["calibration"]["by_confidence"] = [{"label": "60-69", "count": 5}]
    flags = kpi_service.compute_flags([scan], [rollup])
    codes = {f["code"]: f["level"] for f in flags}
    assert codes.get("src_yfinance_ohlcv") == "error"
    assert codes.get("calib_immature") == "warn"
    # errors sort before warns
    assert flags[0]["level"] == "error"


def test_compute_flags_high_skip_ratio():
    scan = _healthy_scan()
    scan["metrics"].update(stocks_scanned=100, stocks_skipped=400)
    flags = kpi_service.compute_flags([scan], [_mature_rollup()])
    assert any(f["code"] == "high_skip" for f in flags)
