"""The equity curve must compound what FOLLOWING the signal returned.

It compounded the stock's raw forward return instead, so a bear signal on a
stock that fell read as a loss:

    one bear signal, price 100 -> 90
    win_rate_pct          100.0   (abs_hit is tone-aware)
    total_return_pct      -10.0   (the curve was not)
    mkt_neutral_return    +10.0   (mkt_neutral_excess is tone-aware)

Three numbers in one panel, two of them agreeing and one disagreeing, on a
curve presented as the outcome of following the signal. `abs_hit` flips for
bear at maturation (`signal_outcome_service:255`) and so does
`mkt_neutral_excess` (line 261); only `fwd_return` stays the underlying's own
return, which is correct for what it is and wrong to compound directly.

The panel already warns that sequential compounding without overlap, sizing
and costs is illustrative. That declared limit does not cover a sign error.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome, Stock
from app.services import detector_performance_service as perf

_SEQ = {"n": 0}


def _outcome(
    db: Session,
    *,
    tone: str,
    fwd_return: float,
    detector: str = "structure_break",
    signal_date: date = date(2026, 6, 1),
) -> None:
    """One matured row, with abs_hit and mkt_neutral_excess stamped the way
    `signal_outcome_service` stamps them — tone-aware, both."""
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"E{k}", exchange="TST", name=f"E{k}")
    db.add(stock)
    db.flush()
    alert = Alert(
        stock_id=stock.id,
        signal_name=detector,
        signal_date=signal_date,
        triggered_at=datetime.now(UTC),
        trigger_price=100.0,
        snapshot="{}",
    )
    db.add(alert)
    db.flush()
    hit = 1 if ((tone == "bull" and fwd_return > 0) or (tone == "bear" and fwd_return < 0)) else 0
    excess = fwd_return if tone == "bull" else -fwd_return
    db.add(
        SignalOutcome(
            alert_id=alert.id,
            stock_id=stock.id,
            detector=detector,
            signal_date=signal_date,
            tone=tone,
            horizon_days=21,
            entry_close=100.0,
            forward_close=100.0 * (1 + fwd_return),
            fwd_return=fwd_return,
            mkt_neutral_excess=excess,
            abs_hit=hit,
            mkt_neutral_hit=1 if excess > 0 else 0,
        )
    )
    db.commit()


class TestABearSignalOnAFallingStockIsAWin:
    def test_the_curve_goes_UP(self, db: Session):
        _outcome(db, tone="bear", fwd_return=-0.10)

        curve = perf.compute_equity_curve(db)

        assert curve["total_return_pct"] == pytest.approx(10.0)

    def test_the_curve_agrees_with_the_win_rate(self, db: Session):
        # The pairing that was on screen: 100% wins, -10% equity.
        _outcome(db, tone="bear", fwd_return=-0.10)

        curve = perf.compute_equity_curve(db)

        assert curve["win_rate_pct"] == 100.0
        assert curve["total_return_pct"] > 0

    def test_the_average_return_is_directional_too(self, db: Session):
        _outcome(db, tone="bear", fwd_return=-0.10)

        assert perf.compute_equity_curve(db)["avg_return_pct"] == pytest.approx(10.0)

    def test_a_bear_signal_on_a_RISING_stock_is_a_loss(self, db: Session):
        _outcome(db, tone="bear", fwd_return=0.10)

        curve = perf.compute_equity_curve(db)

        assert curve["win_rate_pct"] == 0.0
        assert curve["total_return_pct"] == pytest.approx(-10.0)


class TestBullIsUnchanged:
    def test_a_bull_signal_on_a_rising_stock_still_compounds_up(self, db: Session):
        _outcome(db, tone="bull", fwd_return=0.10)

        assert perf.compute_equity_curve(db)["total_return_pct"] == pytest.approx(10.0)

    def test_a_bull_signal_on_a_falling_stock_still_loses(self, db: Session):
        _outcome(db, tone="bull", fwd_return=-0.10)

        assert perf.compute_equity_curve(db)["total_return_pct"] == pytest.approx(-10.0)


class TestTheTwoLegsAgree:
    def test_absolute_and_market_neutral_point_the_same_way_on_a_bear_win(
        self, db: Session
    ):
        # The market-neutral leg was already right; the absolute one is what
        # contradicted it. Neither should be negative here.
        _outcome(db, tone="bear", fwd_return=-0.10)

        curve = perf.compute_equity_curve(db)

        assert curve["total_return_pct"] > 0
        assert curve["mkt_neutral_return_pct"] > 0

    def test_a_mixed_book_nets_out_by_direction_not_by_price(self, db: Session):
        # A bull that rose 10% and a bear that fell 10% are two wins, so the
        # book is up — under the old rule they cancelled to roughly zero.
        _outcome(db, tone="bull", fwd_return=0.10)
        _outcome(db, tone="bear", fwd_return=-0.10, signal_date=date(2026, 7, 1))

        curve = perf.compute_equity_curve(db)

        assert curve["win_rate_pct"] == 100.0
        assert curve["total_return_pct"] > 15.0


class TestDrawdown:
    def test_a_drawdown_is_measured_on_the_directional_curve(self, db: Session):
        # Two bear wins then a bear loss: the dip is the loss, not the rise.
        _outcome(db, tone="bear", fwd_return=-0.10, signal_date=date(2026, 6, 1))
        _outcome(db, tone="bear", fwd_return=0.20, signal_date=date(2026, 7, 1))

        curve = perf.compute_equity_curve(db)

        # Peak 1.10, then 1.10 * 0.80 = 0.88 → 20% off the peak.
        assert curve["max_drawdown_pct"] == pytest.approx(20.0)
