"""`recompute_one` — the per-stock refresh button, previously untested.

It raised `KeyError: 'confidence'` on every stock that had a signal in the
last 14 days. `_recent_signal_facets` has returned {"strength", "tone"} since
the Forza/Probabilità split; the twin call in `finalize` was updated at the
time and this one was missed.

The failure is shaped so that neither the suite nor the live database showed
it: the branch only runs when `fac is not None`, so it broke exactly on the
stocks that HAVE a recent signal — the interesting ones — and no test
exercised that branch at all.
"""
import json
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, OhlcvDaily, Stock
from app.services import technical_score_service as svc


def _stock_with_history(db, ticker="AAA", bars=150):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    start = date.today() - timedelta(days=bars)
    for i in range(bars):
        p = 100.0 + i * 0.5
        db.add(OhlcvDaily(
            stock_id=s.id, date=start + timedelta(days=i),
            open=p, high=p + 1, low=p - 1, close=p, volume=1000.0,
        ))
    db.commit()
    return s


def _recent_signal(db, stock, strength=82.0, tone="bull"):
    db.add(Alert(
        stock_id=stock.id, trigger_price=100.0, signal_name="sr_flip",
        triggered_at=datetime.now(UTC) - timedelta(days=2),
        snapshot=json.dumps({"strength": strength, "tone": tone}),
    ))
    db.commit()


class TestTheCrash:
    def test_a_stock_with_a_recent_signal_recomputes(self, db):
        """THE BUG. Before the fix this raised KeyError: 'confidence',
        surfacing as an unhandled 500 from the refresh button."""
        s = _stock_with_history(db)
        _recent_signal(db, s, strength=82.0)

        row = svc.recompute_one(db, s.id)
        db.commit()

        assert row is not None
        assert row.signals == 82.0

    def test_a_stock_with_no_recent_signal_still_works(self, db):
        """The branch that always worked — kept so a future edit cannot fix
        one side and break the other, which is how this arose."""
        s = _stock_with_history(db, ticker="BBB")

        row = svc.recompute_one(db, s.id)
        db.commit()

        assert row is not None
        assert row.signals is None

    def test_the_strongest_recent_signal_wins(self, db):
        s = _stock_with_history(db, ticker="CCC")
        _recent_signal(db, s, strength=64.0)
        _recent_signal(db, s, strength=91.0)

        row = svc.recompute_one(db, s.id)
        db.commit()

        assert row.signals == 91.0

    def test_a_legacy_snapshot_without_strength_is_read_too(self, db):
        """Pre-split rows carry only "confidence". The facet builder coalesces
        the two; this asserts recompute_one benefits from that rather than
        going blank."""
        s = _stock_with_history(db, ticker="DDD")
        db.add(Alert(
            stock_id=s.id, trigger_price=100.0, signal_name="sr_flip",
            triggered_at=datetime.now(UTC) - timedelta(days=1),
            snapshot=json.dumps({"confidence": 77.0, "tone": "bull"}),
        ))
        db.commit()

        row = svc.recompute_one(db, s.id)
        db.commit()

        assert row.signals == 77.0

    def test_too_little_history_returns_none(self, db):
        s = _stock_with_history(db, ticker="EEE", bars=10)
        assert svc.recompute_one(db, s.id) is None
