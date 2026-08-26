"""Setups must close eventually, whatever their conditions still say.

`_EXPIRE_AFTER_DAYS` measures staleness from `last_seen_at`, which every scan
refreshes while the conditions hold — so a setup whose conditions PERSIST was
never expired at all. Measured in production on 2026-08-26: 1,420 active
setups, 715 of them oversold_reversal, not one of which had ever resolved.
"Oversold and within 8% of a support" is a state a stock can sit in for
months, and the row sat there with it.
"""
from datetime import UTC, date, datetime, timedelta

from app.models import Stock
from app.models.scan_run import KIND_ALERTS_SCAN, ScanRun
from app.models.stock_setup import STATUS_ACTIVE, STATUS_EXPIRED, StockSetup
from app.services.setup_service import _EXPIRE_AFTER_DAYS, _MAX_AGE_DAYS, expire_stale_setups

TODAY = date(2026, 8, 26)
NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def _scans(db, n=5):
    """expire_stale_setups refuses to age anything out on a quiet pipeline."""
    for i in range(n):
        db.add(ScanRun(
            kind=KIND_ALERTS_SCAN, trigger="cron", status="success",
            started_at=NOW - timedelta(days=1), completed_at=NOW - timedelta(hours=i + 1),
            progress_done=0, progress_total=0,
        ))
    db.commit()


def _setup(db, n, *, first_days_ago, last_days_ago, detector="oversold_reversal"):
    stock = Stock(ticker=f"T{n}", exchange="NASDAQ", name=f"T{n}", country="US")
    db.add(stock)
    db.flush()
    row = StockSetup(
        stock_id=stock.id, detector=detector, tone="bull",
        proximity=0.8, convenience=70.0, missing="la barra deve girare",
        factors_json="{}", annotations_json="{}", status=STATUS_ACTIVE,
        first_seen_at=NOW - timedelta(days=first_days_ago),
        last_seen_at=NOW - timedelta(days=last_days_ago),
        shortlisted=True,
    )
    db.add(row)
    db.commit()
    return row


class TestTheCeiling:
    def test_a_setup_refreshed_every_day_still_closes(self, db):
        """THE BUG. Seen today, so never stale — and pending since well before
        the ceiling. Before this it lived forever."""
        _scans(db)
        row = _setup(db, 1, first_days_ago=_MAX_AGE_DAYS + 2, last_days_ago=0)

        expire_stale_setups(db, today=TODAY)
        db.commit()
        db.refresh(row)
        assert row.status == STATUS_EXPIRED
        assert row.resolved_at is not None

    def test_a_young_setup_seen_today_is_left_alone(self, db):
        _scans(db)
        row = _setup(db, 2, first_days_ago=3, last_days_ago=0)

        expire_stale_setups(db, today=TODAY)
        db.commit()
        db.refresh(row)
        assert row.status == STATUS_ACTIVE

    def test_the_staleness_rule_still_works(self, db):
        """Young enough for the ceiling, but not re-observed: the original
        reason for expiry has to keep working."""
        _scans(db)
        row = _setup(db, 3, first_days_ago=_EXPIRE_AFTER_DAYS + 3,
                     last_days_ago=_EXPIRE_AFTER_DAYS + 1)

        expire_stale_setups(db, today=TODAY)
        db.commit()
        db.refresh(row)
        assert row.status == STATUS_EXPIRED

    def test_a_setup_exactly_at_the_ceiling_survives_one_more_day(self, db):
        # Boundary: the cap is "older than", not "at least".
        _scans(db)
        row = _setup(db, 4, first_days_ago=_MAX_AGE_DAYS - 1, last_days_ago=0)

        expire_stale_setups(db, today=TODAY)
        db.commit()
        db.refresh(row)
        assert row.status == STATUS_ACTIVE

    def test_expired_rows_are_kept_not_deleted(self, db):
        """An expired setup is half of the conversion rate. Deleting them
        would leave only the successes on record."""
        _scans(db)
        _setup(db, 5, first_days_ago=_MAX_AGE_DAYS + 5, last_days_ago=0)

        expire_stale_setups(db, today=TODAY)
        db.commit()
        assert db.query(StockSetup).count() == 1


class TestQuietPipelineGuard:
    def test_nothing_ages_out_when_no_scans_ran(self, db):
        """The guard that already protected the staleness rule has to protect
        the ceiling too: the app being down for a month is not the same as a
        setup failing to resolve."""
        row = _setup(db, 6, first_days_ago=_MAX_AGE_DAYS + 10, last_days_ago=0)

        assert expire_stale_setups(db, today=TODAY) == 0
        db.commit()
        db.refresh(row)
        assert row.status == STATUS_ACTIVE
