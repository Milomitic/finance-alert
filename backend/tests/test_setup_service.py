"""Setup lifecycle: the wait is measured, and the measurement is honest.

Setups make no claim about the market, so they can't be validated like a
signal. What they CAN be held to is doing what they say: converting into the
signal they anticipate, with a lead time that is actually counted. These tests
pin that bookkeeping — especially the ways it could silently flatter itself.
"""
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, Stock, StockSetup
from app.models.stock_setup import STATUS_ACTIVE, STATUS_CONVERTED, STATUS_EXPIRED
from app.services import setup_service
from app.signals.setups.base import SetupMatch, convenience


def _match(detector="oversold_reversal", tone="bull", proximity=0.85, **factors):
    return SetupMatch(
        detector=detector, tone=tone, proximity=proximity,
        missing="la barra deve girare",
        factors=factors or {"rsi_extremity": 0.8},
    )


def _stock(db, ticker="TSET"):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def test_reobserving_a_setup_updates_it_and_keeps_the_original_start(db):
    """THE bookkeeping trap: a setup seen again must not restart its own clock.

    first_seen_at is what lead_days is measured from. If re-detection reset it,
    every setup would report ~0 days of warning and the one number this feature
    exists to produce would be silently zeroed.
    """
    s = _stock(db)
    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match(proximity=0.5))
    db.flush()
    started = row.first_seen_at

    again = setup_service.upsert_setup(db, stock_id=s.id, match=_match(proximity=0.85))
    db.flush()

    assert again.id == row.id, "re-detection must update, not duplicate"
    assert again.first_seen_at == started, "the wait restarted — lead_days would be lost"
    assert again.proximity == 0.85


def test_conversion_records_the_lead_time(db):
    s = _stock(db)
    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    # Backdate the start: the setup has been waiting three days.
    row.first_seen_at = datetime.now(UTC) - timedelta(days=3)
    db.flush()

    alert = Alert(stock_id=s.id, trigger_price=10.0, signal_date=date.today(),
                  signal_name="oversold_reversal", snapshot="{}")
    db.add(alert)
    db.flush()

    converted = setup_service.convert_setups_for_alert(db, alert)
    assert converted is not None
    assert converted.status == STATUS_CONVERTED
    assert converted.lead_days == 3
    assert converted.converted_alert_id == alert.id


def test_a_different_detector_firing_does_not_convert_the_setup(db):
    """Conversion must be detector-specific, or the rate is inflated by any
    unrelated signal that happens to land on the same stock."""
    s = _stock(db)
    setup_service.upsert_setup(db, stock_id=s.id, match=_match("oversold_reversal"))
    db.flush()

    alert = Alert(stock_id=s.id, trigger_price=10.0, signal_date=date.today(),
                  signal_name="volume_breakout", snapshot="{}")
    db.add(alert)
    db.flush()

    assert setup_service.convert_setups_for_alert(db, alert) is None
    row = db.query(StockSetup).one()
    assert row.status == STATUS_ACTIVE


def test_stale_setups_expire_but_are_kept_on_record(db):
    """Expired setups are half the conversion rate. Deleting them would leave
    only successes on file and make the feature look better than it is."""
    s = _stock(db)
    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    row.last_seen_at = datetime.now(UTC) - timedelta(days=30)
    db.flush()

    assert setup_service.expire_stale_setups(db) == 1
    db.flush()
    row = db.query(StockSetup).one()          # still there
    assert row.status == STATUS_EXPIRED


def test_a_setup_that_reforms_after_resolving_starts_a_new_wait(db):
    """Otherwise a setup that converted in March and re-forms in July would
    report a four-month lead time."""
    s = _stock(db)
    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    row.status = STATUS_CONVERTED
    row.first_seen_at = datetime.now(UTC) - timedelta(days=120)
    row.lead_days = 4
    db.flush()

    again = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    assert again.status == STATUS_ACTIVE
    assert again.lead_days is None
    assert (datetime.now(UTC) - again.first_seen_at.replace(tzinfo=UTC)).days == 0


def test_conversion_rate_is_unknown_not_zero_before_anything_resolves(db):
    """0% would read as "setups never work"; the truth is we don't know yet."""
    s = _stock(db)
    setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    stats = setup_service.conversion_stats(db)
    assert stats["active"] == 1
    assert stats["conversion_rate"] is None
    assert stats["avg_lead_days"] is None


# ─── convenience: an ordering score, never a probability ────────────────────

def test_convenience_does_not_penalise_a_stock_for_missing_lens_scores():
    """A stock with no Qualità/Tecnico must not sink below one that has poor
    scores — that would rank on data availability instead of on the setup."""
    m = _match(proximity=0.85, rsi_extremity=0.9)
    without = convenience(m)
    with_poor = convenience(m, technical_composite=5.0, quality_composite=5.0)
    assert without > with_poor


def test_convenience_rewards_the_cross_lens_combination():
    """The user's actual idea: the same panic-sell setup on a strong company
    should rank above the identical one on a weak company."""
    m = _match(proximity=0.85, rsi_extremity=0.9)
    strong = convenience(m, technical_composite=80.0, quality_composite=85.0)
    weak = convenience(m, technical_composite=20.0, quality_composite=15.0)
    assert strong > weak


def test_convenience_ignores_gate_factors():
    """Gates are 1.0 by construction; letting them into the mean would just add
    a constant and compress the ranking everything else provides."""
    plain = convenience(_match(proximity=0.5, rsi_extremity=0.4))
    gated = convenience(_match(proximity=0.5, rsi_extremity=0.4, gate_rsi_extreme=1.0))
    assert plain == gated
