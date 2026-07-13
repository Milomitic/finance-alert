"""score_history: daily snapshot of both composites, idempotent per day."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.models import ScoreHistory, Stock, StockScore, TechnicalScore
from app.services import score_history_service as shs


def _seed(db):
    s = Stock(ticker="HIST", exchange="NASDAQ", name="Hist Co", country="US")
    db.add(s)
    db.flush()
    now = datetime.now(UTC)
    db.add(StockScore(stock_id=s.id, composite=72.0, quality=70.0, profitability=65.0,
                      sustainability=60.0, growth=80.0, value=55.0, sentiment=62.0,
                      risk_tier="moderate", computed_at=now, breakdown="{}"))
    db.add(TechnicalScore(stock_id=s.id, composite=1.2, trend=1.0, momentum=0.8,
                          structure=0.5, volume=0.3, rel_strength=0.6, signals=0.0,
                          posture="bullish", computed_at=now, breakdown="{}"))
    db.commit()
    return s


def test_capture_snapshots_both_lenses(db):
    _seed(db)
    n = shs.capture(db, on=date(2026, 6, 9))
    assert n == 2
    rows = db.execute(select(ScoreHistory)).scalars().all()
    lenses = {r.lens for r in rows}
    assert lenses == {"qualita", "tecnico"}
    q = next(r for r in rows if r.lens == "qualita")
    assert q.composite == 72.0 and '"growth": 80.0' in q.pillars


def test_capture_idempotent_same_day(db):
    _seed(db)
    assert shs.capture(db, on=date(2026, 6, 9)) == 2
    assert shs.capture(db, on=date(2026, 6, 9)) == 0  # already snapshotted today
    assert db.execute(select(func.count()).select_from(ScoreHistory)).scalar() == 2


def test_capture_new_day_adds_again(db):
    _seed(db)
    shs.capture(db, on=date(2026, 6, 9))
    assert shs.capture(db, on=date(2026, 6, 10)) == 2
    assert db.execute(select(func.count()).select_from(ScoreHistory)).scalar() == 4
