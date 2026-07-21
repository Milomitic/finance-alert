"""Tests for the signal equity-curve simulator (service + endpoint).

Seeds the signal_outcomes warehouse directly and checks the cumulative
compounding, filters, and drawdown math.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, SignalOutcome, Stock, User

_SEQ = {"n": 0}


def _mk(
    db: Session,
    *,
    detector: str = "volume_breakout",
    tone: str = "bull",
    regime: str = "bull",
    strength: int = 80,
    fwd_return: float = 0.05,
    excess: float = 0.03,
    abs_hit: int = 1,
    horizon_days: int = 21,
    signal_date: date = date(2026, 6, 1),
) -> None:
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"E{k}", exchange="TST", name=f"E{k}")
    db.add(stock)
    db.flush()
    alert = Alert(
        stock_id=stock.id,
        signal_name=detector,
        signal_date=signal_date,
        trigger_price=100.0,
        snapshot=json.dumps({"tone": tone, "strength": strength}),
    )
    db.add(alert)
    db.flush()
    db.add(
        SignalOutcome(
            alert_id=alert.id,
            stock_id=stock.id,
            detector=detector,
            signal_date=signal_date,
            tone=tone,
            horizon_days=horizon_days,
            entry_close=100.0,
            forward_close=100.0 * (1 + fwd_return),
            fwd_return=fwd_return,
            universe_mean_fwd=fwd_return - excess,
            mkt_neutral_excess=excess,
            abs_hit=abs_hit,
            mkt_neutral_hit=1,
            regime_at_signal=regime,
            strength=strength,
            probability=55,
        )
    )


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_empty_warehouse(client):
    b = client.get("/api/rule-performance/equity-curve").json()
    assert b["n_signals"] == 0
    assert b["points"] == []
    assert b["total_return_pct"] == 0.0


def test_compound_equity(db, client):
    # three +5% signals on distinct dates → 1.05^3 ≈ 1.157625 → +15.76%
    for i in range(3):
        _mk(db, fwd_return=0.05, signal_date=date(2026, 6, 1 + i))
    db.commit()
    b = client.get("/api/rule-performance/equity-curve").json()
    assert b["n_signals"] == 3
    assert b["total_return_pct"] == pytest.approx(15.76, abs=0.05)
    assert len(b["points"]) == 3
    assert b["points"][-1]["equity"] == pytest.approx(1.1576, abs=0.001)
    assert b["win_rate_pct"] == 100.0


def test_detector_filter_and_list(db, client):
    _mk(db, detector="volume_breakout", fwd_return=0.05)
    _mk(db, detector="rsi_divergence", tone="bear", fwd_return=-0.02, signal_date=date(2026, 6, 2))
    db.commit()
    b = client.get("/api/rule-performance/equity-curve?detector=volume_breakout").json()
    assert b["n_signals"] == 1
    # the dropdown list always reflects the full set, unfiltered
    assert set(b["detectors"]) >= {"volume_breakout", "rsi_divergence"}


def test_horizon_filter(db, client):
    _mk(db, horizon_days=5, fwd_return=0.05)
    _mk(db, horizon_days=21, fwd_return=0.10, signal_date=date(2026, 6, 2))
    db.commit()
    b5 = client.get("/api/rule-performance/equity-curve?horizon_days=5").json()
    assert b5["n_signals"] == 1 and b5["horizon_days"] == 5
    b21 = client.get("/api/rule-performance/equity-curve?horizon_days=21").json()
    assert b21["n_signals"] == 1 and b21["horizon_days"] == 21


def test_max_drawdown(db, client):
    # +10% then -20% → equity 1.1 then 0.88; peak 1.1 → dd = (1.1-0.88)/1.1 ≈ 20%
    _mk(db, fwd_return=0.10, signal_date=date(2026, 6, 1))
    _mk(db, fwd_return=-0.20, abs_hit=0, signal_date=date(2026, 6, 2))
    db.commit()
    b = client.get("/api/rule-performance/equity-curve").json()
    assert b["max_drawdown_pct"] == pytest.approx(20.0, abs=0.1)
    assert b["win_rate_pct"] == 50.0


def test_bad_horizon_falls_back_to_21(db, client):
    _mk(db, horizon_days=21, fwd_return=0.05)
    db.commit()
    b = client.get("/api/rule-performance/equity-curve?horizon_days=99").json()
    assert b["horizon_days"] == 21 and b["n_signals"] == 1
