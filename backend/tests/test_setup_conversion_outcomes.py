"""Did a converted setup go on to be RIGHT?

The setups report card stopped at "it converted". That is the honest floor —
conversion and lead time are facts about the feature that need no market claim
— but it leaves the obvious question unanswered, and answerable: a converted
setup names the alert it became, and that alert may already carry a labeled
outcome in the `signal_outcomes` warehouse.

Two decisions are load-bearing here.

MARKET-NEUTRAL ONLY. The label is `mkt_neutral_hit` — did the signal beat the
universe median in its own direction — never `abs_hit`. Absolute hit counts
the market's drift as the setup's merit: on the live warehouse `sr_flip` bull
reads 57.9% absolute against 51.5% market-neutral, and six of those points are
just being long. Mixing the two bases inside one count would be worse than
either.

PENDING IS ITS OWN BUCKET. A converted setup whose horizon has not elapsed has
no outcome, and neither does one whose trigger date had no universe benchmark.
Neither is a failure, and folding either into "negativo" would invent losses.
"""
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome, Stock
from app.models.stock_setup import STATUS_CONVERTED, STATUS_EXPIRED, StockSetup
from app.services.setup_service import conversion_stats

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
_SEQ = {"n": 0}


def _converted(db: Session, *, mkt_hit: int | None, matured: bool = True, lead: int = 5):
    """A converted setup, its alert, and optionally the alert's outcome row."""
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"S{k}", exchange="NASDAQ", name=f"S{k}")
    db.add(stock)
    db.flush()
    alert = Alert(
        stock_id=stock.id, signal_name="trend_pullback",
        signal_date=date(2026, 6, 1), trigger_price=100.0,
        snapshot=json.dumps({"tone": "bull", "strength": 70}),
    )
    db.add(alert)
    db.flush()
    if matured:
        db.add(SignalOutcome(
            alert_id=alert.id, stock_id=stock.id, detector="trend_pullback",
            signal_date=date(2026, 6, 1), tone="bull", horizon_days=21,
            entry_close=100.0, forward_close=105.0, fwd_return=0.05,
            universe_mean_fwd=0.0 if mkt_hit is not None else None,
            mkt_neutral_excess=0.05 if mkt_hit is not None else None,
            abs_hit=1, mkt_neutral_hit=mkt_hit, strength=70, probability=50,
        ))
    db.add(StockSetup(
        stock_id=stock.id, detector="trend_pullback", tone="bull",
        proximity=0.8, convenience=70.0, missing="—", factors_json="{}",
        status=STATUS_CONVERTED, shortlisted=True,
        first_seen_at=NOW - timedelta(days=10), last_seen_at=NOW,
        resolved_at=NOW, lead_days=lead, converted_alert_id=alert.id,
    ))
    db.commit()


def _expired(db: Session):
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"E{k}", exchange="NASDAQ", name=f"E{k}")
    db.add(stock)
    db.flush()
    db.add(StockSetup(
        stock_id=stock.id, detector="trend_pullback", tone="bear",
        proximity=0.5, convenience=40.0, missing="—", factors_json="{}",
        status=STATUS_EXPIRED, shortlisted=True,
        first_seen_at=NOW - timedelta(days=20), last_seen_at=NOW, resolved_at=NOW,
    ))
    db.commit()


def test_converted_setups_are_split_by_their_signal_outcome(db: Session):
    _converted(db, mkt_hit=1)
    _converted(db, mkt_hit=1)
    _converted(db, mkt_hit=0)

    s = conversion_stats(db)

    assert s["converted"] == 3
    assert s["converted_positive"] == 2
    assert s["converted_negative"] == 1
    assert s["converted_pending"] == 0


def test_a_converted_setup_whose_horizon_has_not_elapsed_is_pending(db: Session):
    """No outcome row yet. Counting it as negative would invent a loss."""
    _converted(db, mkt_hit=1, matured=False)

    s = conversion_stats(db)

    assert s["converted_positive"] == 0
    assert s["converted_negative"] == 0
    assert s["converted_pending"] == 1


def test_an_unbenchmarked_outcome_is_pending_not_negative(db: Session):
    """The row matured but the trigger date had no universe median, so there
    is no market-neutral label. Absent, not failed."""
    _converted(db, mkt_hit=None)

    s = conversion_stats(db)

    assert s["converted_negative"] == 0
    assert s["converted_pending"] == 1


def test_the_split_is_market_neutral_never_absolute(db: Session):
    """The seeded row has abs_hit=1 and mkt_neutral_hit=0 — it went up, but by
    less than the market. Reading the absolute label would score that a win
    and quietly credit the setup with the market's drift."""
    _converted(db, mkt_hit=0)

    s = conversion_stats(db)

    assert s["converted_positive"] == 0
    assert s["converted_negative"] == 1


def test_totals_cover_both_views_of_the_page(db: Session):
    """The page has two tabs; each needs its own total, and they must add up
    to what the feature has ever tracked."""
    _converted(db, mkt_hit=1)
    _expired(db)
    _expired(db)

    s = conversion_stats(db)

    assert s["closed"] == 3            # the "Esiti" tab
    assert s["total"] == s["active"] + s["closed"]


def test_lead_time_reports_a_range_not_only_a_mean(db: Session):
    """One mean hides whether the warning was consistently a week or wildly
    between a day and a month — and the wait is the whole product."""
    for lead in (2, 4, 30):
        _converted(db, mkt_hit=1, lead=lead)

    s = conversion_stats(db)

    assert s["median_lead_days"] == 4       # the mean would be 12
    assert s["lead_days_min"] == 2
    assert s["lead_days_max"] == 30


def test_an_empty_table_reports_unknown_rather_than_zero(db: Session):
    s = conversion_stats(db)

    assert s["converted_positive"] == 0
    assert s["median_lead_days"] is None
    assert s["lead_days_min"] is None
    assert s["conversion_rate"] is None


@pytest.mark.parametrize("field", [
    "total", "closed", "converted_positive", "converted_negative",
    "converted_pending", "median_lead_days", "lead_days_min", "lead_days_max",
    "active_bull", "active_bear",
])
def test_every_new_field_is_present(db: Session, field: str):
    assert field in conversion_stats(db)
