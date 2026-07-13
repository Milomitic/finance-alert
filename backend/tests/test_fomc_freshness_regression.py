"""Regression guards for commit 83a5631
("calendar: FOMC freshness fix + Forexfactory consensus + Ultimo/Atteso/Sorpresa unification").

The commit introduced two correlated invariants on the calendar
aggregator's macro path that we want to lock in:

1. **Freshness (`_enrich_with_fred_value`)** — hardcoded macros (FOMC,
   etc., from `calendar_macros._MACRO_EVENTS`) must be enriched with
   the latest matching `MacroObservation` even when that observation
   was published on the *same* day as the event itself. The lookup
   uses `MacroObservation.date <= ev.date` so a same-day DFEDTARU print
   on FOMC day IS attached as `prev_value`. Before the fix, FOMC was
   sourced from FEDFUNDS (monthly-averaged, lagged ~1 month) and the
   panel showed a stale value on the day of the rate decision.

2. **Forexfactory consensus (`_enrich_with_forexfactory`)** — the FF
   weekly XML's `forecast` populates `expected_value` ("Atteso") and
   the FF `actual` populates `actual_value` ("Ultimo dal feed"). The
   two are STRICTLY separate slots; pre-release events must not have
   their consensus leak into `actual_value`. Surprise is only computed
   when BOTH expected AND actual are non-None and expected != 0.

We pre-seed `forexfactory_consensus._CACHE` directly to avoid the HTTP
fetch (the cache is `(timestamp, [FFEvent])` with a 30-min TTL — a
fresh timestamp + synthetic events is the standard test stub).

We rely on the curated FOMC date 2026-05-14 in
`calendar_macros._MACRO_EVENTS` for the macro under test.
"""
from __future__ import annotations

import time
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import MacroObservation, MacroSeries
from app.services import calendar_service, forexfactory_consensus, stock_fundamentals_service
from app.services.calendar_service import MacroEventDC
from app.services.forexfactory_consensus import FFEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Curated FOMC date that lives in calendar_macros._MACRO_EVENTS for
# the May 2026 window. The aggregator emits this regardless of DB seed
# because it falls through the hardcoded fallback path (no FRED
# release_date row) — exactly what _enrich_with_fred_value targets.
_FOMC_DATE = date(2026, 5, 14)
_FOMC_LABEL = "FOMC rate decision"


@pytest.fixture(autouse=True)
def _isolate_caches():
    """Each test starts with empty fundamentals AND forexfactory caches.
    We don't want a previous test's FF stub leaking, and we don't want
    real HTTP being attempted because the cache is None."""
    stock_fundamentals_service._CACHE.clear()
    forexfactory_consensus.clear_cache()
    yield
    stock_fundamentals_service._CACHE.clear()
    forexfactory_consensus.clear_cache()


def _stub_ff_cache(events: list[FFEvent]) -> None:
    """Inject synthetic FFEvents into the in-memory cache with a fresh
    timestamp so `_get_events()` returns them WITHOUT making an HTTP
    request. The 30-min TTL means time.time() is plenty fresh."""
    forexfactory_consensus._CACHE = (time.time(), events)


def _seed_fomc_series_with_observation(
    db: Session, *, value: float, on_date: date,
) -> MacroSeries:
    """Insert a `MacroSeries` whose label matches `FOMC rate decision`
    plus one `MacroObservation` at `on_date`. The aggregator's
    `_enrich_with_fred_value` matches the series by `label`."""
    series = MacroSeries(
        fred_series_id="DFEDTARU",
        fred_release_id=None,
        label=_FOMC_LABEL,
        region="US",
        importance="high",
        unit="pct",
    )
    db.add(series)
    db.flush()
    db.add(MacroObservation(series_id=series.id, date=on_date, value=value))
    db.commit()
    return series


def _get_fomc_event(events: list) -> MacroEventDC:
    """Locate the FOMC MacroEventDC from a get_events() result."""
    fomc = [
        e for e in events
        if isinstance(e, MacroEventDC) and e.date == _FOMC_DATE and e.label == _FOMC_LABEL
    ]
    assert len(fomc) == 1, f"expected exactly one FOMC event, got {len(fomc)}: {fomc}"
    return fomc[0]


# ---------------------------------------------------------------------------
# Invariant 1: Freshness — same-day MacroObservation IS attached
# ---------------------------------------------------------------------------

def test_fomc_same_day_observation_is_attached_as_prev_value(db: Session):
    """Regression guard for the FEDFUNDS → DFEDTARU swap. If the lookup
    used `<` instead of `<=`, a same-day observation would be skipped
    and the FOMC card would render a stale value (the prior month's
    average). The fix uses `<=` so same-day prints land on the card.
    """
    # Don't stub FF — we only care about the FRED-side enrichment here.
    _stub_ff_cache([])  # empty FF cache → no expected/actual leakage

    _seed_fomc_series_with_observation(db, value=5.50, on_date=_FOMC_DATE)

    events = calendar_service.get_events(
        db, _FOMC_DATE, _FOMC_DATE,
        kinds={"macro"},
    )
    fomc = _get_fomc_event(events)

    assert fomc.prev_value == pytest.approx(5.50)
    assert fomc.prev_date == _FOMC_DATE
    assert fomc.unit == "pct"


def test_fomc_skips_observations_after_event_date(db: Session):
    """If a future observation exists in the DB (e.g. a backfill / dry-run
    seed sitting past the event date), it must NOT be returned as the
    FOMC's `prev_value`. The query gates on `<= ev.date`, so an
    observation dated _FOMC_DATE+1 is invisible to a FOMC event at
    _FOMC_DATE.
    """
    _stub_ff_cache([])

    series = _seed_fomc_series_with_observation(
        db, value=5.50, on_date=_FOMC_DATE,
    )
    # Add a bogus observation AFTER the FOMC date — must be filtered out.
    db.add(MacroObservation(
        series_id=series.id, date=date(2026, 5, 20), value=99.99,
    ))
    db.commit()

    events = calendar_service.get_events(
        db, _FOMC_DATE, _FOMC_DATE,
        kinds={"macro"},
    )
    fomc = _get_fomc_event(events)
    # The 99.99 row dated 2026-05-20 is after FOMC; the latest observation
    # available *up to and including* 2026-05-14 is the 5.50 print.
    assert fomc.prev_value == pytest.approx(5.50)
    assert fomc.prev_date == _FOMC_DATE


# ---------------------------------------------------------------------------
# Invariant 2: Forexfactory consensus does NOT leak into actual_value
# ---------------------------------------------------------------------------

def test_future_fomc_consensus_populates_expected_not_actual(db: Session):
    """Pre-release event: FF feed has a forecast but no actual. The
    aggregator must populate `expected_value` (Atteso) and leave
    `actual_value` (Ultimo dal feed) and `surprise_pct` strictly None.
    Conflating these two slots was the root of the "Ultimo shows the
    consensus instead of the actual" bug.
    """
    _stub_ff_cache([
        FFEvent(
            title="Federal Funds Rate",
            country="USD",
            date=_FOMC_DATE,
            impact="High",
            forecast="5.25",
            previous="5.00",
            actual=None,  # pre-release → no actual yet
        ),
    ])

    events = calendar_service.get_events(
        db, _FOMC_DATE, _FOMC_DATE,
        kinds={"macro"},
    )
    fomc = _get_fomc_event(events)

    assert fomc.expected_value == pytest.approx(5.25), \
        "FF forecast must populate expected_value"
    assert fomc.actual_value is None, \
        "actual_value must NOT be backfilled from the consensus — separate slots"
    assert fomc.surprise_pct is None, \
        "surprise requires both expected and actual; no actual → no surprise"


def test_post_release_fomc_populates_actual_and_surprise(db: Session):
    """Post-release event: FF feed has both forecast and actual. The
    aggregator must populate both slots and compute
    surprise_pct = (actual - expected) / |expected| * 100.
    This is the "Sorpresa" axis and the test pins the formula.
    """
    _stub_ff_cache([
        FFEvent(
            title="Federal Funds Rate",
            country="USD",
            date=_FOMC_DATE,
            impact="High",
            forecast="5.25",
            previous="5.00",
            actual="5.50",  # post-release → actual is in
        ),
    ])

    events = calendar_service.get_events(
        db, _FOMC_DATE, _FOMC_DATE,
        kinds={"macro"},
    )
    fomc = _get_fomc_event(events)

    assert fomc.expected_value == pytest.approx(5.25)
    assert fomc.actual_value == pytest.approx(5.50)
    # (5.50 - 5.25) / |5.25| * 100 = 4.7619...
    assert fomc.surprise_pct == pytest.approx(((5.50 - 5.25) / 5.25) * 100)


def test_forexfactory_unmapped_label_leaves_consensus_fields_none(db: Session):
    """Sanity: when the FF cache contains events that don't match our
    `_FF_LABEL_MAP` (different country, different title regex), the
    macro emission must NOT pick up stray expected/actual values.
    Guards against accidental cross-event leakage in the regex matcher.
    """
    _stub_ff_cache([
        # GBP event — matches the BoE Bank Rate mapping, NOT FOMC.
        FFEvent(
            title="Official Bank Rate",
            country="GBP",
            date=_FOMC_DATE,
            impact="High",
            forecast="4.50",
            previous="4.50",
            actual="4.25",
        ),
    ])

    events = calendar_service.get_events(
        db, _FOMC_DATE, _FOMC_DATE,
        kinds={"macro"},
    )
    fomc = _get_fomc_event(events)

    # The FOMC event must NOT inherit the BoE values.
    assert fomc.expected_value is None
    assert fomc.actual_value is None
    assert fomc.surprise_pct is None


def test_post_release_fomc_with_fred_observation_keeps_both_axes(db: Session):
    """Combined invariant: a same-day FOMC where BOTH
    (a) `MacroObservation` has a value AND
    (b) FF feed has forecast+actual
    must produce a fully-populated event:
      prev_value (from FRED) AND expected_value/actual_value/surprise_pct
      (from FF) all live concurrently — they don't shadow each other.
    """
    _seed_fomc_series_with_observation(db, value=5.50, on_date=_FOMC_DATE)
    _stub_ff_cache([
        FFEvent(
            title="Federal Funds Rate",
            country="USD",
            date=_FOMC_DATE,
            impact="High",
            forecast="5.25",
            previous="5.00",
            actual="5.50",
        ),
    ])

    events = calendar_service.get_events(
        db, _FOMC_DATE, _FOMC_DATE,
        kinds={"macro"},
    )
    fomc = _get_fomc_event(events)

    # FRED-side
    assert fomc.prev_value == pytest.approx(5.50)
    assert fomc.prev_date == _FOMC_DATE
    # FF-side
    assert fomc.expected_value == pytest.approx(5.25)
    assert fomc.actual_value == pytest.approx(5.50)
    assert fomc.surprise_pct == pytest.approx(((5.50 - 5.25) / 5.25) * 100)
