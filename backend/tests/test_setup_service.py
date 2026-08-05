"""Setup lifecycle: the wait is measured, and the measurement is honest.

Setups make no claim about the market, so they can't be validated like a
signal. What they CAN be held to is doing what they say: converting into the
signal they anticipate, with a lead time that is actually counted. These tests
pin that bookkeeping — especially the ways it could silently flatter itself.
"""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import Alert, Stock, StockSetup
from app.models.stock_setup import STATUS_ACTIVE, STATUS_CONVERTED, STATUS_EXPIRED
from app.services import setup_service
from app.signals.setups.base import SetupMatch, convenience


def _match(detector="oversold_reversal", tone="bull", proximity=0.85,
           distance_atr=None, **factors):
    return SetupMatch(
        detector=detector, tone=tone, proximity=proximity,
        missing="la barra deve girare",
        distance_atr=distance_atr,
        factors=factors or {"rsi_extremity": 0.8},
    )


def _successful_scans(db, n: int):
    """Expiry is guarded on scans having actually run — see the guard below."""
    from app.models import ScanRun
    for _ in range(n):
        db.add(ScanRun(kind="alerts_scan", trigger="cron", status="success",
                       completed_at=datetime.now(UTC)))
    db.flush()


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
    # Both observations must clear the emission floor, otherwise the first one
    # is never stored and this would be testing nothing.
    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match(proximity=0.80))
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

    _successful_scans(db, 3)

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


# ─── Emission gate (first production scan: 1214 setups over ~1000 stocks) ────

def test_a_weak_setup_is_not_stored_at_all(db):
    """Setups shipped with no bar and the first real scan produced more than
    one per stock — the whole market rather than a watchlist."""
    s = _stock(db)
    weak = _match(proximity=0.30, rsi_extremity=0.2)
    assert setup_service.upsert_setup(db, stock_id=s.id, match=weak) is None
    db.flush()
    assert db.query(StockSetup).count() == 0


def test_a_setup_that_decays_below_the_bar_is_dropped_not_kept(db):
    """Otherwise the list only ever grows: things that stop deserving
    attention would sit there forever."""
    s = _stock(db)
    setup_service.upsert_setup(db, stock_id=s.id, match=_match(proximity=0.85))
    db.flush()
    assert db.query(StockSetup).count() == 1

    setup_service.upsert_setup(db, stock_id=s.id, match=_match(proximity=0.30, rsi_extremity=0.1))
    db.flush()
    assert db.query(StockSetup).count() == 0, "a decayed setup must leave the list"


def test_the_cap_keeps_the_strongest_and_preserves_detector_diversity(db):
    """squeeze_expansion matched 291 names on the first scan — ~30% of any
    universe has compressed bands. Without a per-detector cap one common
    pattern buries the rarer ones, which are the reason to look at all."""
    from app.core.config import settings

    all_scores = []
    for i in range(settings.setup_max_per_detector + 6):
        st = _stock(db, ticker=f"SQZ{i}")
        # convenience rises with i, so the last ones are the strongest
        row = setup_service.upsert_setup(
            db, stock_id=st.id,
            match=_match("squeeze_expansion", proximity=0.85, rsi_extremity=0.70 + i * 0.015),
        )
        all_scores.append(row.convenience)
    other = _stock(db, ticker="RARE")
    setup_service.upsert_setup(db, stock_id=other.id,
                               match=_match("oversold_reversal", proximity=0.85))
    db.flush()

    setup_service.prune_to_top_per_detector(db)
    db.flush()

    kept = db.query(StockSetup).filter_by(
        detector="squeeze_expansion", shortlisted=True
    ).all()
    assert len(kept) == settings.setup_max_per_detector
    # Dropped rows SURVIVE with their history — deleting them would restart
    # the wait of anything that re-enters the shortlist later.
    assert db.query(StockSetup).filter_by(
        detector="squeeze_expansion", shortlisted=False
    ).count() == 6
    # The survivors must be the STRONGEST, not an arbitrary slice: every kept
    # score has to beat every dropped one.
    assert sorted((r.convenience for r in kept), reverse=True) == sorted(
        all_scores, reverse=True
    )[: settings.setup_max_per_detector]
    assert db.query(StockSetup).filter_by(
        detector="oversold_reversal", shortlisted=True
    ).count() == 1, "the rare detector must survive the common one's cap"


def test_nothing_expires_while_the_pipeline_is_quiet(db):
    """`last_seen_at` only advances when a scan re-observes a setup, so an
    outage looks exactly like decay. Ageing setups out during a pipeline
    problem would inflate the expired count — the mirror image of the bug the
    keep-expired-rows rule prevents."""
    s = _stock(db)
    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    row.last_seen_at = datetime.now(UTC) - timedelta(days=30)
    db.flush()

    # No successful scans recorded: the silence is ours, not the market's.
    assert setup_service.expire_stale_setups(db) == 0
    assert db.query(StockSetup).one().status == STATUS_ACTIVE


def test_a_setup_that_re_enters_the_shortlist_keeps_its_original_wait(db):
    """THE reason the cap flags instead of deleting: scores cluster, so rows
    oscillate around the boundary. If dropping meant deleting, every re-entry
    would restart the clock and avg_lead_days would trend to zero for reasons
    that have nothing to do with the market."""
    s = _stock(db)
    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    row.first_seen_at = datetime.now(UTC) - timedelta(days=5)
    row.shortlisted = False           # fell out of the top N
    db.flush()

    again = setup_service.upsert_setup(db, stock_id=s.id, match=_match())
    db.flush()
    assert again.id == row.id
    assert (datetime.now(UTC) - again.first_seen_at.replace(tzinfo=UTC)).days == 5


def test_stats_count_only_what_was_actually_surfaced(db):
    """A setup the user never saw made no claim to them, so its outcome must
    not move the conversion rate the page advertises."""
    shown = _stock(db, "SHOWN")
    hidden = _stock(db, "HIDDEN")
    a = setup_service.upsert_setup(db, stock_id=shown.id, match=_match())
    b = setup_service.upsert_setup(db, stock_id=hidden.id, match=_match())
    db.flush()
    a.status, b.status = STATUS_CONVERTED, STATUS_CONVERTED
    b.shortlisted = False
    db.flush()

    assert setup_service.conversion_stats(db)["converted"] == 1


def test_distance_atr_survives_the_round_trip(db):
    """The wiring, end to end: detector → SetupMatch → row.

    `proximity` cannot separate two setups of the same detector — it is the
    same number for all of them by construction. `distance_atr` is the value
    that can, so it has to actually reach the database; a field computed in
    the detector and dropped on the way to the row would look identical in
    every unit test of the calculation itself.
    """
    s = Stock(ticker="AAA", name="A", exchange="X")
    db.add(s)
    db.flush()

    row = setup_service.upsert_setup(db, stock_id=s.id, match=_match(distance_atr=0.42))
    assert row.distance_atr == pytest.approx(0.42)

    # And it must be REFRESHED on re-detection, not written once: price moves,
    # so a stale distance is worse than none — it would rank a setup that has
    # drifted away as if it were still on the doorstep.
    again = setup_service.upsert_setup(db, stock_id=s.id, match=_match(distance_atr=1.9))
    assert again.id == row.id
    assert again.distance_atr == pytest.approx(1.9)


def test_distance_atr_is_none_for_triggers_without_a_level(db):
    """squeeze_expansion waits on volatility re-expanding — there is no price
    level to be near. None must survive as None rather than becoming a 0 that
    would sort it to the top of "closest to firing"."""
    s = Stock(ticker="BBB", name="B", exchange="X")
    db.add(s)
    db.flush()
    row = setup_service.upsert_setup(
        db, stock_id=s.id, match=_match(detector="squeeze_expansion", distance_atr=None)
    )
    assert row.distance_atr is None
