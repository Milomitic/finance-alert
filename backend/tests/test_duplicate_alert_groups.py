"""Which alert rows are re-readings of one event, and which must not be touched.

FA-052. `evaluate_signals` minted a row on every scan pass once an event's
outcome had matured (FA-051 stopped that); 668 rows across 9,034 alerts are
the residue, and they cannot simply be deleted by resemblance.

Three tables point at `alerts`, and their delete rules are the whole problem:

    signal_outcomes.alert_id       ON DELETE CASCADE   (and UNIQUE)
    positions.alert_id             ON DELETE SET NULL
    stock_setups.converted_alert_id ON DELETE SET NULL

CASCADE is loud. SET NULL is silent: a blind delete would raise nothing and
leave positions with no signal provenance and setups "converted" to nothing,
with `lead_days` measuring a link that no longer exists.

So the detector's job is not only to find the groups — it is to say which ones
carry something that must be decided by a person. A group that reports a
blocker is data, not a failure.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, Position, SignalOutcome, Stock, StockSetup
from app.scripts import repair_duplicate_alerts as repair
from app.services.alert_service import find_duplicate_alert_groups


def _stock(db, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def _alert(db, stock, *, signal_date, tone="bull", price=50.0, minutes=0,
           detector="candle_reversal") -> Alert:
    a = Alert(
        stock_id=stock.id, trigger_price=price, signal_date=signal_date,
        signal_name=detector, snapshot=json.dumps({"tone": tone}),
        triggered_at=datetime(2026, 7, 16, 9, 0, tzinfo=UTC) + timedelta(minutes=minutes),
        archived_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    db.add(a)
    db.flush()
    return a


def _outcome(db, alert, *, signal_date=None) -> SignalOutcome:
    """`signal_date` defaults to the alert's own — pass a different one to
    build the pre-freeze-guard misalignment."""
    o = SignalOutcome(
        alert_id=alert.id, stock_id=alert.stock_id, detector=alert.signal_name,
        signal_date=signal_date or alert.signal_date, tone="bull", horizon_days=5,
        entry_close=50.0, forward_close=52.0, fwd_return=0.04, abs_hit=1,
    )
    db.add(o)
    db.flush()
    return o


# ─── 1. Quali righe sono lo STESSO evento ────────────────────────────────


def test_two_rows_on_one_bar_are_one_group_oldest_elected(db) -> None:
    """The original is the EARLIEST by triggered_at — the row that recorded the
    event when it happened. Electing the newest would keep the re-reading and
    discard the record."""
    s = _stock(db, "DUP_BASE")
    first = _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    second = _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    third = _alert(db, s, signal_date=date(2026, 7, 9), minutes=60)
    db.commit()

    groups = find_duplicate_alert_groups(db)
    assert len(groups) == 1
    g = groups[0]
    assert g.original_id == first.id
    assert sorted(g.excess_ids) == sorted([second.id, third.id])
    assert g.blockers == []


def test_a_different_bar_is_a_different_event(db) -> None:
    """A candle reversal six days later, on another bar, IS another event.

    This is the boundary FA-051's fix draws and it is deliberate: 82 pairs of
    distinct dates inside the cooldown exist in production against 668
    same-bar rows. Collapsing them would destroy real signals."""
    s = _stock(db, "DUP_OTHERDAY")
    _alert(db, s, signal_date=date(2026, 7, 9))
    _alert(db, s, signal_date=date(2026, 7, 15))
    db.commit()

    assert find_duplicate_alert_groups(db) == []


def test_opposite_tones_on_one_bar_are_not_duplicates(db) -> None:
    """Bull and bear from one detector on one bar contradict each other; that
    is a finding, not a duplication."""
    s = _stock(db, "DUP_TONES")
    _alert(db, s, signal_date=date(2026, 7, 9), tone="bull")
    _alert(db, s, signal_date=date(2026, 7, 9), tone="bear")
    db.commit()

    assert find_duplicate_alert_groups(db) == []


def test_different_detectors_on_one_bar_are_not_duplicates(db) -> None:
    s = _stock(db, "DUP_DETECTORS")
    _alert(db, s, signal_date=date(2026, 7, 9), detector="candle_reversal")
    _alert(db, s, signal_date=date(2026, 7, 9), detector="gap_and_go")
    db.commit()

    assert find_duplicate_alert_groups(db) == []


def test_a_clean_warehouse_yields_nothing(db) -> None:
    """The floor. Without it every assertion above could hold vacuously on a
    detector that returns the empty list no matter what."""
    s = _stock(db, "DUP_CLEAN")
    _alert(db, s, signal_date=date(2026, 7, 9))
    db.commit()

    assert find_duplicate_alert_groups(db) == []


# ─── 2. Cosa impedisce la bonifica automatica ────────────────────────────


def test_an_excess_row_holding_a_position_blocks_its_group(db) -> None:
    """`positions.alert_id` is ON DELETE SET NULL: deleting the row would raise
    nothing and silently strip the position of its provenance."""
    s = _stock(db, "DUP_POS")
    first = _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    second = _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    db.add(Position(stock_id=s.id, alert_id=second.id, side="long",
                    entry_price=50.0))
    db.commit()

    (g,) = find_duplicate_alert_groups(db)
    assert g.original_id == first.id
    assert "posizione" in g.blockers


def test_an_excess_row_closing_a_setup_blocks_its_group(db) -> None:
    """`stock_setups.converted_alert_id` is also SET NULL, and losing it takes
    `lead_days` with it — the number that says how much warning the feature
    actually gave."""
    s = _stock(db, "DUP_SETUP")
    _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    second = _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    db.add(StockSetup(
        stock_id=s.id, detector="candle_reversal", tone="bull", proximity=0.8,
        convenience=70.0, missing="x", status="converted",
        converted_alert_id=second.id, lead_days=4,
    ))
    db.commit()

    (g,) = find_duplicate_alert_groups(db)
    assert "setup" in g.blockers


def test_a_misaligned_original_outcome_blocks_its_group(db) -> None:
    """⚠️ The case that justifies looking at the divergent outcomes one by one.

    Before the freeze-post-esito guard existed, a cooldown refresh could move
    an alert's `signal_date` forward AFTER its outcome had matured, so the
    outcome describes a bar the alert no longer shows. 18 such rows exist in
    production, all matured in June/July and none since August.

    In those groups the ORIGINAL carries the stale measurement and an excess
    row carries the one that matches the bar on screen — so "keep the first,
    delete the rest" would keep the wrong number. The detector must refuse and
    say so rather than pick."""
    s = _stock(db, "DUP_STALE")
    first = _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    _outcome(db, first, signal_date=date(2026, 6, 25))   # barra precedente
    db.commit()

    (g,) = find_duplicate_alert_groups(db)
    assert "esito-disallineato" in g.blockers


def test_an_aligned_original_outcome_does_not_block(db) -> None:
    """The other side of that boundary: 658 of the 668 excess rows carry an
    outcome identical to the original's, and those groups are ordinary."""
    s = _stock(db, "DUP_ALIGNED")
    first = _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    second = _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    _outcome(db, first)
    _outcome(db, second)
    db.commit()

    (g,) = find_duplicate_alert_groups(db)
    assert g.blockers == []


# ─── 3. Lo script, ESEGUITO ──────────────────────────────────────────────


def test_the_read_only_pass_deletes_nothing(db) -> None:
    """The default. Every repair script in this repo reads before it writes,
    and this one deletes rows that carry matured measurements."""
    s = _stock(db, "DUP_DRY")
    _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    db.commit()

    repair.main(argv=[], db=db)

    assert db.query(Alert).count() == 2


def test_apply_removes_the_excess_and_its_outcome(db) -> None:
    """⚠️ This test exists because the dead-code gate caught `main` as a
    function no test had ever executed — and it is the function that deletes
    production rows. A repair path nobody has run is not a repair path.

    It also pins the CASCADE: the excess row's outcome must go with it, or the
    warehouse would hold a measurement of an alert that no longer exists."""
    s = _stock(db, "DUP_APPLY")
    first = _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    second = _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    _outcome(db, first)
    _outcome(db, second)
    db.commit()

    repair.main(argv=["--apply"], db=db)

    superstiti = db.query(Alert).all()
    assert [a.id for a in superstiti] == [first.id]
    assert db.query(SignalOutcome).count() == 1          # il CASCADE ha agito
    assert db.query(SignalOutcome).one().alert_id == first.id


def test_apply_refuses_a_blocked_group(db) -> None:
    """The blockers are not advisory. A group carrying a position keeps every
    row, `--apply` or not, because `positions.alert_id` is SET NULL and the
    delete would strip the provenance without raising anything."""
    s = _stock(db, "DUP_BLOCKED")
    first = _alert(db, s, signal_date=date(2026, 7, 9), minutes=0)
    second = _alert(db, s, signal_date=date(2026, 7, 9), minutes=30)
    db.add(Position(stock_id=s.id, alert_id=second.id, side="long",
                    entry_price=50.0))
    db.commit()

    repair.main(argv=["--apply"], db=db)

    assert {a.id for a in db.query(Alert).all()} == {first.id, second.id}
    assert db.query(Position).one().alert_id == second.id


def test_a_clean_warehouse_makes_the_script_say_so(db) -> None:
    """The floor on the script itself: with nothing to do it must take the
    early return rather than fall through the reporting path on empty lists."""
    s = _stock(db, "DUP_NOOP")
    _alert(db, s, signal_date=date(2026, 7, 9))
    db.commit()

    repair.main(argv=["--apply"], db=db)

    assert db.query(Alert).count() == 1
