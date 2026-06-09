"""signal_outcomes maturation: write ONE labeled row per matured signal alert
(abs hit + market-neutral + regime), no-look-ahead, idempotent."""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.models import Alert, OhlcvDaily, SignalOutcome, Stock
from app.services import signal_outcome_service as sos


def _seed(db, *, closes: list[float], sig_idx: int, tone: str = "bull"):
    s = Stock(ticker="OUTC", exchange="NASDAQ", name="Outcome Co", country="US")
    db.add(s)
    db.flush()
    d0 = date(2026, 1, 1)
    days = [d0 + timedelta(days=i) for i in range(len(closes))]
    for d, c in zip(days, closes):
        db.add(OhlcvDaily(stock_id=s.id, date=d, open=c, high=c + 1,
                          low=c - 1, close=c, volume=1_000_000))
    a = Alert(
        stock_id=s.id, trigger_price=closes[sig_idx], signal_date=days[sig_idx],
        signal_name="trend_pullback",
        snapshot=json.dumps({"tone": tone, "strength": 70, "probability": 55}),
    )
    db.add(a)
    db.flush()
    return s, a, days


def test_matures_one_row_with_abs_hit_and_is_idempotent(db, monkeypatch):
    # Horizon 3 bars; signal at idx 2; forward bar idx 5. Rising closes → bull hit.
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    closes = [10, 11, 12, 13, 14, 15, 16, 17]
    _s, a, _days = _seed(db, closes=closes, sig_idx=2, tone="bull")
    db.commit()

    added = sos.mature_outcomes(db)
    assert added == 1
    row = db.execute(select(SignalOutcome)).scalars().one()
    assert row.alert_id == a.id
    assert row.detector == "trend_pullback"
    assert row.horizon_days == 3
    assert row.entry_close == 12.0       # close at signal bar (idx 2)
    assert row.forward_close == 15.0     # close 3 bars later (idx 5)
    assert row.abs_hit == 1              # bull, 15 > 12
    assert row.fwd_return > 0
    assert row.strength == 70 and row.probability == 55

    # Idempotent: re-running adds nothing.
    assert sos.mature_outcomes(db) == 0


def test_not_matured_when_horizon_not_elapsed(db, monkeypatch):
    # Horizon 5 but only 2 bars after the signal → not matured, no row.
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 5)
    closes = [10, 11, 12, 13]  # signal at idx 1, forward idx 6 doesn't exist
    _seed(db, closes=closes, sig_idx=1, tone="bull")
    db.commit()
    assert sos.mature_outcomes(db) == 0
    assert db.execute(select(SignalOutcome)).scalars().first() is None


def test_bear_miss_recorded(db, monkeypatch):
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 2)
    # Bear signal but price RISES → miss (abs_hit 0).
    closes = [10, 11, 12, 13, 14]
    _seed(db, closes=closes, sig_idx=1, tone="bear")
    db.commit()
    sos.mature_outcomes(db)
    row = db.execute(select(SignalOutcome)).scalars().one()
    assert row.tone == "bear"
    assert row.abs_hit == 0  # bear, price rose
