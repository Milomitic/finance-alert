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
    for d, c in zip(days, closes, strict=False):
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


def test_windowed_universe_mean_matches_full_load(db, monkeypatch):
    """The windowed universe load (date >= min_trigger - buffer) must yield the
    SAME market-neutral benchmark at the trigger date as a full-history load —
    this is the core exactness claim of the mature_outcomes windowing."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    # Two stocks, 60 bars each; signal near the end (idx 50) so the windowed
    # load trims ~40 pre-trigger bars while keeping the forward window.
    s1 = Stock(ticker="UNIVA", exchange="NASDAQ", name="A", country="US")
    s2 = Stock(ticker="UNIVB", exchange="NASDAQ", name="B", country="US")
    db.add_all([s1, s2]); db.flush()
    d0 = date(2026, 1, 1)
    for s, base in ((s1, 10.0), (s2, 50.0)):
        for i in range(60):
            c = base + i  # steady rise
            db.add(OhlcvDaily(stock_id=s.id, date=d0 + timedelta(days=i),
                              open=c, high=c + 1, low=c - 1, close=c, volume=1_000_000))
    sig_day = d0 + timedelta(days=50)
    db.add(Alert(stock_id=s1.id, trigger_price=60.0, signal_date=sig_day,
                 signal_name="trend_pullback",
                 snapshot=json.dumps({"tone": "bull", "strength": 70, "probability": 55})))
    db.commit()

    # Windowed value (what mature_outcomes actually stores).
    sos.mature_outcomes(db)
    row = db.execute(select(SignalOutcome)).scalars().one()
    windowed_mean = row.universe_mean_fwd

    # Full-history value: same computation without the `since` window.
    full = sos._load_universe_closes(db)
    full_means = sos._universe_fwd_means(full, 3)
    assert windowed_mean is not None
    assert full_means[sig_day] == windowed_mean          # exact, not approximate
    assert row.regime_at_signal in ("bull", "bear")      # EMA used full history
    assert row.mkt_neutral_excess is not None


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
