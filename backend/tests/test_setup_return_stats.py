"""A conversion rate says the setup fired. It does not say it was worth taking.

`conversion_stats` could already answer "does this feature convert, and with
how much warning". It could not answer the two questions a person actually
asks of a setup: what did it EARN, and which setups are the good ones. Both are
added here, under the honesty rules this repo already applies to every other
efficacy number.

Three of those rules are load-bearing and each is pinned below:

  - the return is reported market-neutral AND absolute, side by side. CLAUDE.md
    records `high52_momentum` at 54.0 absolute against 50.5 market-neutral,
    where 3.5 of the 4 points above a coin flip were simply being long. One
    number alone lets that hide.
  - the MEDIAN leads. Forward returns are right-skewed, so a single large
    winner drags the mean up and describes a typical setup that does not exist.
  - the interval is sized on `independent_blocks`, not the row count. Setups
    that fire days apart share most of their forward window.
"""

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome, Stock, StockSetup
from app.models.stock_setup import STATUS_CONVERTED, STATUS_EXPIRED
from app.services.setup_service import conversion_stats

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_SEQ = {"n": 0}


def _converted(
    db: Session,
    *,
    detector: str = "trend_pullback",
    mkt_hit: int | None = 1,
    excess: float | None = 0.05,
    fwd: float = 0.05,
    signal_day: date = date(2026, 6, 1),
    matured: bool = True,
) -> None:
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"C{k}", exchange="NASDAQ", name=f"C{k}")
    db.add(stock)
    db.flush()
    alert = Alert(
        stock_id=stock.id, signal_name=detector, signal_date=signal_day,
        trigger_price=100.0, snapshot=json.dumps({"tone": "bull", "strength": 70}),
    )
    db.add(alert)
    db.flush()
    if matured:
        db.add(SignalOutcome(
            alert_id=alert.id, stock_id=stock.id, detector=detector,
            signal_date=signal_day, tone="bull", horizon_days=21,
            entry_close=100.0, forward_close=100.0 * (1 + fwd), fwd_return=fwd,
            universe_mean_fwd=0.0, mkt_neutral_excess=excess,
            abs_hit=1 if fwd > 0 else 0, mkt_neutral_hit=mkt_hit,
            strength=70, probability=50,
        ))
    db.add(StockSetup(
        stock_id=stock.id, detector=detector, tone="bull",
        proximity=0.8, convenience=70.0, missing="—", factors_json="{}",
        status=STATUS_CONVERTED, shortlisted=True,
        first_seen_at=NOW - timedelta(days=10), last_seen_at=NOW,
        resolved_at=NOW, lead_days=5, converted_alert_id=alert.id,
    ))
    db.commit()


def _expired(db: Session, *, detector: str = "trend_pullback") -> None:
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"X{k}", exchange="NASDAQ", name=f"X{k}")
    db.add(stock)
    db.flush()
    db.add(StockSetup(
        stock_id=stock.id, detector=detector, tone="bear",
        proximity=0.5, convenience=40.0, missing="—", factors_json="{}",
        status=STATUS_EXPIRED, shortlisted=True,
        first_seen_at=NOW - timedelta(days=20), last_seen_at=NOW, resolved_at=NOW,
    ))
    db.commit()


class TestTheReturnIsReportedTwice:
    def test_market_neutral_and_absolute_are_both_present(self, db: Session):
        # Publishing only one of them is how a bull-tone setup books the
        # market's drift as its own merit.
        _converted(db, excess=0.02, fwd=0.09)

        s = conversion_stats(db)

        assert s["median_excess_pct"] == 2.0
        assert s["median_return_pct"] == 9.0

    def test_they_are_allowed_to_disagree(self, db: Session):
        # The whole point. A setup that rode a rising market shows a large
        # absolute return and a small excess, and both must reach the screen.
        _converted(db, excess=0.01, fwd=0.12)

        s = conversion_stats(db)

        assert s["median_return_pct"] > s["median_excess_pct"]

    def test_the_median_leads_and_the_mean_sits_beside_it(self, db: Session):
        # Right-skewed by construction: four ordinary results and one outlier.
        for _ in range(4):
            _converted(db, excess=0.01, fwd=0.01)
        _converted(db, excess=1.00, fwd=1.00)

        s = conversion_stats(db)

        assert s["median_excess_pct"] == 1.0
        # The mean is dragged far above every typical observation, which is
        # exactly why it cannot be the headline.
        assert s["mean_excess_pct"] > 15.0

    def test_no_matured_outcome_means_no_return_rather_than_zero(self, db: Session):
        # 0.0% would read as "the setups earned nothing". They have not
        # finished yet, which is a different statement.
        _converted(db, matured=False)

        s = conversion_stats(db)

        assert s["median_excess_pct"] is None
        assert s["median_return_pct"] is None


class TestTheHitRateCarriesItsOwnDoubt:
    def test_it_reports_a_rate_with_the_sample_that_produced_it(self, db: Session):
        _converted(db, mkt_hit=1)
        _converted(db, mkt_hit=1)
        _converted(db, mkt_hit=0)

        s = conversion_stats(db)

        assert s["converted_judged"] == 3
        assert s["converted_hit_rate"] == 66.7

    def test_the_interval_is_sized_on_independent_windows_not_rows(self, db: Session):
        # Ten setups on the SAME day share one forward window entirely, so they
        # are one observation. A row-count interval would read as ten.
        for _ in range(10):
            _converted(db, mkt_hit=1, signal_day=date(2026, 6, 1))

        s = conversion_stats(db)

        assert s["converted_judged"] == 10
        assert s["converted_effective_n"] == 1
        assert s["converted_low_confidence"] is True

    def test_a_thin_rate_is_flagged_and_still_shown(self, db: Session):
        # Hiding it would be worse: a number the reader can distrust beats a
        # blank they cannot interrogate.
        _converted(db, mkt_hit=1)

        s = conversion_stats(db)

        assert s["converted_hit_rate"] == 100.0
        assert s["converted_low_confidence"] is True
        assert s["converted_ci_low"] < 100.0

    def test_a_pending_outcome_is_not_a_loss(self, db: Session):
        _converted(db, mkt_hit=1)
        _converted(db, mkt_hit=None, excess=None)

        s = conversion_stats(db)

        assert s["converted_judged"] == 1
        assert s["converted_hit_rate"] == 100.0


class TestPerDetector:
    def test_it_separates_detectors_instead_of_averaging_them(self, db: Session):
        # The aggregate cannot say which setup to trust: a detector that always
        # converts and one that never does average to something describing
        # neither.
        _converted(db, detector="sr_flip", mkt_hit=1)
        _converted(db, detector="sr_flip", mkt_hit=1)
        _expired(db, detector="squeeze")
        _expired(db, detector="squeeze")

        rows = {r["detector"]: r for r in conversion_stats(db)["by_detector"]}

        assert rows["sr_flip"]["conversion_rate"] == 100.0
        assert rows["squeeze"]["conversion_rate"] == 0.0

    def test_every_rate_travels_with_its_denominator(self, db: Session):
        _converted(db, detector="sr_flip", mkt_hit=1)
        _expired(db, detector="sr_flip")

        row = conversion_stats(db)["by_detector"][0]

        # 50% on two setups means nothing without the two.
        assert row["resolved"] == 2
        assert row["converted"] == 1
        assert row["expired"] == 1
        assert row["judged"] == 1

    def test_rows_lead_with_the_ones_that_have_something_to_say(self, db: Session):
        _converted(db, detector="rara", mkt_hit=1)
        for _ in range(4):
            _converted(db, detector="frequente", mkt_hit=1)

        rows = conversion_stats(db)["by_detector"]

        assert rows[0]["detector"] == "frequente"

    def test_a_detector_with_no_matured_outcome_has_no_rate(self, db: Session):
        _converted(db, detector="nuovo", matured=False)

        row = conversion_stats(db)["by_detector"][0]

        assert row["judged"] == 0
        assert row["hit_rate"] is None
        assert row["median_excess_pct"] is None

    def test_an_expired_only_detector_still_appears(self, db: Session):
        # Dropping it would flatter the feature: a setup family that never
        # converts is precisely what a report card should show.
        _expired(db, detector="mai")

        rows = {r["detector"]: r for r in conversion_stats(db)["by_detector"]}

        assert "mai" in rows
        assert rows["mai"]["conversion_rate"] == 0.0
