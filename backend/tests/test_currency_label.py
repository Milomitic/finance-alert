"""A price in pounds must not wear a label that says pence.

`currency_units` already owned the NUMBER side of the pence problem: LSE
listings arrive from yfinance in pence and every stored price is divided by
100 at ingest. What had no owner was the LABEL. Six catalog rows kept
yfinance's raw `GBp` beside a value that is pounds, which is a factor-of-100
lie the moment anything renders the two together -- and nothing did, which is
why it survived.

Measured on production before this was written: all 99 `.L` stocks carry
`ohlcv_in_pounds = true`, and the six GBp-labelled ones sit at 5.57 to 35.04,
inside the 0.80 to 175.70 range of the rows already labelled GBP. Pence would
be a hundred times larger. The numbers were never the problem.
"""
import io

from sqlalchemy.orm import Session

from app.models import Stock
from app.services.currency_units import (
    major_unit_currency,
    scale_minor_to_major,
)
from app.services.seed_service import seed_index_from_csv


class TestTheLabelFollowsTheStoredNumber:
    def test_both_pence_spellings_become_pounds(self):
        assert major_unit_currency("GBp") == "GBP"
        assert major_unit_currency("GBX") == "GBP"

    def test_it_is_not_just_always_gbp(self):
        # The negative control. Without it the function could return "GBP"
        # unconditionally and every assertion above would still pass.
        assert major_unit_currency("USD") == "USD"
        assert major_unit_currency("EUR") == "EUR"
        assert major_unit_currency("HKD") == "HKD"

    def test_pounds_are_left_alone(self):
        # A few LSE mainboard names quote directly in pounds. Rewriting them
        # would be harmless here but would hide a real drift elsewhere.
        assert major_unit_currency("GBP") == "GBP"

    def test_absence_stays_absence(self):
        # Market assets -- indices, FX, crypto -- have no listing currency,
        # and an index level is not money. Inventing one would be worse than
        # showing none.
        assert major_unit_currency(None) is None


class TestTheTwoHalvesAreNotInterchangeable:
    """The trap this module now has two functions for.

    `scale_minor_to_major` converts a NUMBER and must run exactly once, at
    ingest. `major_unit_currency` converts a LABEL and is idempotent. Running
    the first one twice is the ×100 bug in reverse; running the second one
    twice is free. Nothing in the type signatures says so, so it is pinned.
    """

    def test_scaling_the_number_twice_is_wrong(self):
        once = scale_minor_to_major("GBp", 1359.0)
        assert once == 13.59
        # The second call would need the currency to still read GBp, which is
        # exactly what `major_unit_currency` prevents downstream.
        twice = scale_minor_to_major("GBp", once)
        assert twice != once

    def test_relabelling_twice_is_free(self):
        assert major_unit_currency(major_unit_currency("GBp")) == "GBP"


class TestTheSeedBoundaryNormalises:
    """Where the six bad rows came from.

    `catalog_refresh_service` writes a hardcoded 'GBP' for the FTSE source and
    never touches currency on an existing row, so the raw value could only
    have entered through the CSV seed. Repairing the rows without closing this
    door would let the next import put them straight back.
    """

    CSV = (
        "ticker,name,exchange,sector,industry,country,currency\n"
        "SHEL.L,Shell plc,LSE,Energy,Oil & Gas,GB,GBp\n"
        "AZN.L,AstraZeneca PLC,LSE,Health Care,Pharma,GB,GBP\n"
    )

    def _seed(self, db: Session) -> None:
        seed_index_from_csv(
            db, io.StringIO(self.CSV),
            index_code="UKX", index_name="FTSE 100", country="GB",
        )
        db.commit()

    def test_a_pence_row_is_stored_as_pounds_on_create(self, db: Session):
        self._seed(db)

        shel = db.query(Stock).filter_by(ticker="SHEL.L").one()
        assert shel.currency == "GBP"

    def test_a_pounds_row_is_untouched(self, db: Session):
        # Same negative control as above, but through the real write path.
        self._seed(db)

        azn = db.query(Stock).filter_by(ticker="AZN.L").one()
        assert azn.currency == "GBP"

    def test_a_re_import_cannot_reintroduce_it(self, db: Session):
        # The update branch is a SEPARATE assignment in `_upsert_stock`, so
        # fixing only the create branch would leave the door open on every
        # subsequent seed -- which is how an idempotent importer quietly
        # undoes a migration.
        self._seed(db)
        db.query(Stock).filter_by(ticker="SHEL.L").one().currency = "GBp"
        db.commit()

        self._seed(db)

        assert db.query(Stock).filter_by(ticker="SHEL.L").one().currency == "GBP"
