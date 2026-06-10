"""Tests for the signal drift / decay monitor.

Covers:
  - the Wilson-interval helper (known values, n=0 sentinel, widening at small n);
  - the service over SYNTHETIC alerts + ohlcv run through the REAL maturation
    pipeline (`signal_outcome_service.mature_outcomes` → `signal_outcomes`
    warehouse → drift):
      * a detector whose recent matured alerts mostly WORKED → high recent rate
        and (vs a low base rate, clearing the Wilson band) flagged "improving";
      * one that mostly FAILED → low recent rate, flagged "decaying";
      * a small-n case with an extreme deviation that must NOT flag;
      * not-yet-matured alerts are excluded;
      * alerts not yet matured INTO THE WAREHOUSE are invisible to drift
        (the "as of the last scan" freshness contract);
  - the read-only endpoint (auth + envelope shape).

Calibration is monkeypatched onto a `CalibrationMap` we control so the test
doesn't depend on the live `signal_calibration.json`.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, OhlcvDaily, Stock, User
from app.services import signal_drift_service as drift
from app.services import signal_outcome_service as sos
from app.signals.calibration_map import CalibrationMap

# --------------------------------------------------------------------------- #
# Wilson interval — pure unit tests                                           #
# --------------------------------------------------------------------------- #

def test_wilson_n_zero_is_uninformative():
    assert drift.wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_known_value_10_of_10():
    # 10/10 successes: textbook Wilson 95% lower bound ≈ 0.7225, upper = 1.0.
    lo, hi = drift.wilson_interval(10, 10)
    assert hi == pytest.approx(1.0, abs=1e-9)
    assert lo == pytest.approx(0.7225, abs=1e-3)


def test_wilson_centered_for_half():
    # 50/100: interval straddles 0.5 symmetrically, ~[0.404, 0.596].
    lo, hi = drift.wilson_interval(50, 100)
    assert lo == pytest.approx(0.404, abs=5e-3)
    assert hi == pytest.approx(0.596, abs=5e-3)
    assert (lo + hi) / 2 == pytest.approx(0.5, abs=1e-9)


def test_wilson_widens_as_n_shrinks():
    # Same proportion (1/2 vs 50/100): the small-n band must be much wider.
    lo_s, hi_s = drift.wilson_interval(1, 2)
    lo_l, hi_l = drift.wilson_interval(50, 100)
    assert (hi_s - lo_s) > (hi_l - lo_l)


def test_wilson_stays_in_unit_interval_at_extremes():
    for hits, n in [(0, 5), (5, 5), (0, 1), (3, 3)]:
        lo, hi = drift.wilson_interval(hits, n)
        assert 0.0 <= lo <= hi <= 1.0


# --------------------------------------------------------------------------- #
# Synthetic-data harness                                                      #
# --------------------------------------------------------------------------- #

def _mk_stock(db: Session, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="TST", name=ticker)
    db.add(s)
    db.flush()
    return s


def _mk_bars(
    db: Session,
    stock_id: int,
    *,
    start: date,
    n_bars: int,
    trigger_offset: int,
    horizon_days: int,
    hit: bool,
    tone: str,
) -> date:
    """Build `n_bars` consecutive daily bars. The trigger bar sits at index
    `trigger_offset` with close 100. The bar `horizon_days` forward is set so
    the close moves the signalled way (hit) or against it (miss). Every other
    bar sits flat at 100 (irrelevant to the close-to-close check). Returns the
    trigger bar's date (the alert's signal_date).
    """
    trigger_close = 100.0
    forward_idx = trigger_offset + horizon_days
    assert forward_idx < n_bars, "forward bar must exist for a matured alert"
    # bull-hit / bear-miss → up move; bear-hit / bull-miss → down move.
    up = (tone == "bull") == hit
    forward_close = 110.0 if up else 90.0
    trigger_date: date | None = None
    for i in range(n_bars):
        d = start + timedelta(days=i)
        if i == trigger_offset:
            close = trigger_close
            trigger_date = d
        elif i == forward_idx:
            close = forward_close
        else:
            close = trigger_close
        db.add(OhlcvDaily(
            stock_id=stock_id, date=d,
            open=close, high=close + 1, low=close - 1, close=close, volume=1000,
        ))
    assert trigger_date is not None
    return trigger_date


def _mk_alert(db: Session, stock_id: int, name: str, tone: str, signal_date: date) -> None:
    db.add(Alert(
        stock_id=stock_id,
        signal_name=name,
        signal_date=signal_date,
        trigger_price=100.0,
        snapshot=json.dumps({"tone": tone}),
    ))


def _patch_calibration(monkeypatch, base_rates: dict[str, float], horizon_days: int = 5):
    """Point the service at a CalibrationMap with the given per-detector base
    rates (percent) + a shared horizon_days."""
    data = {
        "detectors": {
            name: {"base_rate": br, "horizon_days": horizon_days}
            for name, br in base_rates.items()
        }
    }
    cmap = CalibrationMap(data)
    monkeypatch.setattr(drift, "get_calibration", lambda: cmap)
    return cmap


# --------------------------------------------------------------------------- #
# Service behaviour                                                           #
# --------------------------------------------------------------------------- #

def test_detector_that_mostly_worked_is_improving(db: Session, monkeypatch):
    """40 recent matured alerts, ~90% hit, base rate 50 → recent high, base
    below the Wilson band → flagged, direction 'improving'."""
    hz = 5
    _patch_calibration(monkeypatch, {"volume_breakout": 50.0}, horizon_days=hz)
    start = date.today() - timedelta(days=60)
    n = 40
    n_hits = 36  # 90%
    for k in range(n):
        s = _mk_stock(db, f"WIN{k}")
        sig_d = _mk_bars(
            db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
            horizon_days=hz, hit=(k < n_hits), tone="bull",
        )
        _mk_alert(db, s.id, "volume_breakout", "bull", sig_d)
    db.commit()
    sos.mature_outcomes(db)  # the real production pipeline: warehouse → drift

    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    assert len(rows) == 1
    r = rows[0]
    assert r["detector"] == "volume_breakout"
    assert r["n_matured"] == n
    assert r["recent_hit_rate"] == pytest.approx(90.0, abs=0.1)
    assert r["base_rate"] == 50.0
    assert r["delta"] == pytest.approx(40.0, abs=0.1)
    # 36/40 Wilson 95% lower bound ≈ 77% → base 50 is well below it.
    assert r["ci_low"] > 50.0
    assert r["drift_flag"] is True
    assert r["direction"] == "improving"


def test_detector_that_mostly_failed_is_decaying(db: Session, monkeypatch):
    """40 recent matured alerts, ~20% hit, base rate 55 → recent low, base
    above the Wilson band → flagged, direction 'decaying'."""
    hz = 5
    _patch_calibration(monkeypatch, {"oversold_reversal": 55.0}, horizon_days=hz)
    start = date.today() - timedelta(days=60)
    n = 40
    n_hits = 8  # 20%
    for k in range(n):
        s = _mk_stock(db, f"FAIL{k}")
        sig_d = _mk_bars(
            db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
            horizon_days=hz, hit=(k < n_hits), tone="bull",
        )
        _mk_alert(db, s.id, "oversold_reversal", "bull", sig_d)
    db.commit()
    sos.mature_outcomes(db)  # the real production pipeline: warehouse → drift

    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    assert len(rows) == 1
    r = rows[0]
    assert r["recent_hit_rate"] == pytest.approx(20.0, abs=0.1)
    assert r["base_rate"] == 55.0
    # 8/40 Wilson 95% upper bound ≈ 35% → base 55 is above it.
    assert r["ci_high"] < 55.0
    assert r["drift_flag"] is True
    assert r["direction"] == "decaying"


def test_small_sample_does_not_flag_despite_extreme_deviation(db: Session, monkeypatch):
    """Only 6 matured alerts, all MISSED (0% realised) vs base 55. The deviation
    is huge but n < min_n (and the Wilson band at n=6 is very wide), so it must
    NOT be flagged — the whole point of the band is to ignore thin evidence."""
    hz = 5
    _patch_calibration(monkeypatch, {"gap_and_go": 55.0}, horizon_days=hz)
    start = date.today() - timedelta(days=30)
    n = 6
    for k in range(n):
        s = _mk_stock(db, f"TINY{k}")
        sig_d = _mk_bars(
            db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
            horizon_days=hz, hit=False, tone="bull",
        )
        _mk_alert(db, s.id, "gap_and_go", "bull", sig_d)
    db.commit()
    sos.mature_outcomes(db)  # the real production pipeline: warehouse → drift

    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    assert len(rows) == 1
    r = rows[0]
    assert r["n_matured"] == 6
    assert r["recent_hit_rate"] == pytest.approx(0.0, abs=0.1)
    assert r["drift_flag"] is False         # below min_n → never flag
    assert r["direction"] == "stable"


def test_small_sample_below_min_n_even_if_wilson_would_exclude(db: Session, monkeypatch):
    """Belt-and-suspenders: 20 matured alerts, all hit (100%) vs base 50. At
    n=20 the Wilson lower bound (~83%) already excludes 50, but min_n=30 is the
    hard floor → still NOT flagged."""
    hz = 5
    _patch_calibration(monkeypatch, {"rsi_divergence": 50.0}, horizon_days=hz)
    start = date.today() - timedelta(days=30)
    n = 20
    for k in range(n):
        s = _mk_stock(db, f"MID{k}")
        sig_d = _mk_bars(
            db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
            horizon_days=hz, hit=True, tone="bull",
        )
        _mk_alert(db, s.id, "rsi_divergence", "bull", sig_d)
    db.commit()
    sos.mature_outcomes(db)  # the real production pipeline: warehouse → drift

    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    r = rows[0]
    assert r["n_matured"] == 20
    assert r["ci_low"] > 50.0               # Wilson alone WOULD exclude the base
    assert r["drift_flag"] is False         # but min_n gate blocks the flag
    assert r["direction"] == "stable"


def test_not_yet_matured_alerts_are_excluded(db: Session, monkeypatch):
    """An alert whose forward bar doesn't exist yet (horizon not elapsed) must
    be excluded from n_matured — so a brand-new burst of alerts can't move the
    realised rate before any of them has resolved."""
    hz = 5
    _patch_calibration(monkeypatch, {"candle_reversal": 50.0}, horizon_days=hz)
    today = date.today()

    # Matured: trigger 20d ago, plenty of forward bars (all hit).
    for k in range(32):
        s = _mk_stock(db, f"MAT{k}")
        sig_d = _mk_bars(
            db, s.id, start=today - timedelta(days=20), n_bars=hz + 2,
            trigger_offset=0, horizon_days=hz, hit=True, tone="bull",
        )
        _mk_alert(db, s.id, "candle_reversal", "bull", sig_d)

    # Immature: trigger is the LAST stored bar → no forward bar at trigger+hz.
    for k in range(10):
        s = _mk_stock(db, f"IMM{k}")
        last = today
        # Only bars up to and including the trigger; none after.
        for i in range(hz):  # bars BEFORE trigger
            d = last - timedelta(days=hz - i)
            db.add(OhlcvDaily(stock_id=s.id, date=d, open=100, high=101, low=99,
                              close=100, volume=1000))
        db.add(OhlcvDaily(stock_id=s.id, date=last, open=100, high=101, low=99,
                          close=100, volume=1000))  # trigger == last bar
        _mk_alert(db, s.id, "candle_reversal", "bull", last)
    db.commit()
    sos.mature_outcomes(db)  # the real production pipeline: warehouse → drift

    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    r = next(x for x in rows if x["detector"] == "candle_reversal")
    # Only the 32 matured alerts count; the 10 immature ones are dropped.
    assert r["n_matured"] == 32
    assert r["recent_hit_rate"] == pytest.approx(100.0, abs=0.1)


def test_drift_reads_the_warehouse_not_raw_ohlcv(db: Session, monkeypatch):
    """Freshness contract: drift is served from the `signal_outcomes` warehouse
    (populated by `mature_outcomes` at scan end), NOT by replaying OHLCV. Alerts
    whose outcomes haven't been matured into the warehouse yet are invisible —
    the window reflects "as of the last scan", and that lag is by design."""
    hz = 5
    _patch_calibration(monkeypatch, {"volume_breakout": 50.0}, horizon_days=hz)
    start = date.today() - timedelta(days=40)
    for k in range(35):
        s = _mk_stock(db, f"FRESH{k}")
        sig_d = _mk_bars(db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
                         horizon_days=hz, hit=True, tone="bull")
        _mk_alert(db, s.id, "volume_breakout", "bull", sig_d)
    db.commit()

    # No mature_outcomes() yet → warehouse empty → drift sees nothing.
    assert drift.compute_signal_drift(db, window_days=90, min_n=30) == []

    # After the scan-end maturation pass, the same alerts are visible.
    sos.mature_outcomes(db)
    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    assert len(rows) == 1
    assert rows[0]["n_matured"] == 35


def test_archived_and_out_of_window_alerts_excluded(db: Session, monkeypatch):
    """Archived alerts and alerts whose signal_date predates the window are
    excluded; an empty result is returned when nothing qualifies."""
    hz = 5
    _patch_calibration(monkeypatch, {"sr_flip": 50.0}, horizon_days=hz)

    # Out of the 90d window (triggered 200d ago).
    s1 = _mk_stock(db, "OLD")
    sig_old = _mk_bars(db, s1.id, start=date.today() - timedelta(days=200),
                       n_bars=hz + 2, trigger_offset=0, horizon_days=hz,
                       hit=True, tone="bull")
    _mk_alert(db, s1.id, "sr_flip", "bull", sig_old)

    # In window but archived.
    s2 = _mk_stock(db, "ARCH")
    sig_arch = _mk_bars(db, s2.id, start=date.today() - timedelta(days=20),
                        n_bars=hz + 2, trigger_offset=0, horizon_days=hz,
                        hit=True, tone="bull")
    a = Alert(stock_id=s2.id, signal_name="sr_flip", signal_date=sig_arch,
              trigger_price=100.0, snapshot=json.dumps({"tone": "bull"}))
    a.archived_at = datetime.now(UTC)
    db.add(a)
    db.commit()
    sos.mature_outcomes(db)  # the real production pipeline: warehouse → drift

    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    assert rows == []


def test_rows_sorted_by_abs_delta(db: Session, monkeypatch):
    """Two detectors with different |delta| come back sorted largest-first."""
    hz = 5
    _patch_calibration(
        monkeypatch, {"big_move": 50.0, "small_move": 50.0}, horizon_days=hz,
    )
    start = date.today() - timedelta(days=40)

    # big_move: 35/35 hit → delta = +50.
    for k in range(35):
        s = _mk_stock(db, f"BIG{k}")
        sig_d = _mk_bars(db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
                         horizon_days=hz, hit=True, tone="bull")
        _mk_alert(db, s.id, "big_move", "bull", sig_d)
    # small_move: ~17/35 ≈ 48.6% → delta ≈ -1.4.
    for k in range(35):
        s = _mk_stock(db, f"SML{k}")
        sig_d = _mk_bars(db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
                         horizon_days=hz, hit=(k < 17), tone="bull")
        _mk_alert(db, s.id, "small_move", "bull", sig_d)
    db.commit()
    sos.mature_outcomes(db)  # the real production pipeline: warehouse → drift

    rows = drift.compute_signal_drift(db, window_days=90, min_n=30)
    assert [r["detector"] for r in rows] == ["big_move", "small_move"]
    assert abs(rows[0]["delta"]) >= abs(rows[1]["delta"])


def test_summary_counts(db: Session, monkeypatch):
    rows = [
        {"detector": "a", "drift_flag": True, "direction": "decaying", "delta": -20},
        {"detector": "b", "drift_flag": True, "direction": "improving", "delta": 30},
        {"detector": "c", "drift_flag": False, "direction": "stable", "delta": 1},
    ]
    s = drift.drift_summary(rows, window_days=90, min_n=30)
    assert s["n_detectors"] == 3
    assert s["n_flagged"] == 2
    assert s["n_decaying"] == 1
    assert s["n_improving"] == 1
    assert s["window_days"] == 90
    assert s["min_n"] == 30
    assert "computed_at" in s


# --------------------------------------------------------------------------- #
# Endpoint                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_signal_drift_endpoint_requires_auth():
    c = TestClient(app, raise_server_exceptions=True)
    r = c.get("/api/platform/signal-drift")
    assert r.status_code in (401, 403)


def test_signal_drift_endpoint_shape_empty(client: TestClient):
    """No alerts → 200 with an empty detector list and a zeroed summary."""
    r = client.get("/api/platform/signal-drift")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"summary", "detectors"}
    assert body["detectors"] == []
    assert body["summary"]["n_detectors"] == 0
    assert body["summary"]["n_flagged"] == 0
    assert body["summary"]["window_days"] == 90
    assert body["summary"]["min_n"] == 30


def test_signal_drift_endpoint_returns_rows(client: TestClient, db: Session, monkeypatch):
    hz = 5
    _patch_calibration(monkeypatch, {"volume_breakout": 50.0}, horizon_days=hz)
    start = date.today() - timedelta(days=40)
    for k in range(35):
        s = _mk_stock(db, f"EP{k}")
        sig_d = _mk_bars(db, s.id, start=start, n_bars=hz + 2, trigger_offset=0,
                         horizon_days=hz, hit=True, tone="bull")
        _mk_alert(db, s.id, "volume_breakout", "bull", sig_d)
    db.commit()
    sos.mature_outcomes(db)

    r = client.get("/api/platform/signal-drift?window_days=90&min_n=30")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["n_detectors"] == 1
    assert body["summary"]["n_flagged"] == 1
    row = body["detectors"][0]
    assert row["detector"] == "volume_breakout"
    assert row["drift_flag"] is True
    assert row["direction"] == "improving"
    assert set(row.keys()) == {
        "detector", "n_matured", "recent_hit_rate", "base_rate", "delta",
        "ci_low", "ci_high", "drift_flag", "direction", "horizon_days",
    }


def test_signal_drift_endpoint_validates_params(client: TestClient):
    # window_days below the floor (7) → 422.
    assert client.get("/api/platform/signal-drift?window_days=1").status_code == 422
    # min_n below 1 → 422.
    assert client.get("/api/platform/signal-drift?min_n=0").status_code == 422
