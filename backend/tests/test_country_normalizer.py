"""Country ingestion-guard tests.

The `stocks.country` column is normalized to ISO-2; `canonical_country`
is the boundary that keeps re-ingestion (CSV seed, catalog refresh) from
reintroducing full names. Same shape as `test_sector_normalizer` — pure
string function + wiring checks on the seed path.
"""
import io

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock
from app.services import seed_service
from app.services.country_normalizer import canonical_country

# ── Pure-function behavior ────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("United States", "US"),
        ("united states of america", "US"),
        ("USA", "US"),
        ("Italy", "IT"),
        ("Italia", "IT"),
        ("United Kingdom", "GB"),
        ("Great Britain", "GB"),
        ("Germany", "DE"),
        ("Hong Kong", "HK"),
        ("South Korea", "KR"),
        ("China", "CN"),
        ("Japan", "JP"),
        ("Netherlands", "NL"),
        ("Switzerland", "CH"),
        ("Ireland", "IE"),
    ],
)
def test_full_names_fold_to_iso2(raw: str, expected: str) -> None:
    assert canonical_country(raw) == expected


def test_iso2_passthrough_uppercased() -> None:
    # Already-canonical codes pass through; lowercase gets fixed.
    assert canonical_country("US") == "US"
    assert canonical_country("it") == "IT"
    # "EU" is a legitimate catalog value (EuroStoxx pan-European tag).
    assert canonical_country("EU") == "EU"


def test_none_and_blank_are_none() -> None:
    assert canonical_country(None) is None
    assert canonical_country("") is None
    assert canonical_country("   ") is None


def test_unknown_values_pass_through_unchanged() -> None:
    # Never lose data on a label we don't recognize — better an odd value
    # in the column (visible bug) than a silent NULL (hidden bug).
    assert canonical_country("Atlantis") == "Atlantis"


def test_whitespace_and_case_insensitive() -> None:
    assert canonical_country("  united STATES  ") == "US"


# ── Wiring: the CSV seed path can't reinsert full names ───────────────

def _csv(*rows: str) -> io.StringIO:
    header = "ticker,exchange,name,sector,industry,country,currency"
    return io.StringIO("\n".join([header, *rows]))


def test_seed_insert_normalizes_country(db: Session) -> None:
    seed_service.seed_stocks_no_index_from_csv(
        db, _csv("AAPL,NASDAQ,Apple Inc.,Technology,,United States,USD")
    )
    db.commit()
    stock = db.execute(select(Stock).where(Stock.ticker == "AAPL")).scalar_one()
    assert stock.country == "US"


def test_seed_update_normalizes_country(db: Session) -> None:
    # Existing row with a proper ISO-2 country; a re-seed with a full-name
    # country must UPDATE it to the canonical code, not the raw name.
    db.add(Stock(ticker="ENEL.MI", exchange="BIT", name="Enel", country="IT"))
    db.commit()
    seed_service.seed_stocks_no_index_from_csv(
        db, _csv("ENEL.MI,BIT,Enel SpA,Utilities,,Italia,EUR")
    )
    db.commit()
    stock = db.execute(select(Stock).where(Stock.ticker == "ENEL.MI")).scalar_one()
    assert stock.country == "IT"


def test_seed_missing_country_preserves_existing(db: Session) -> None:
    # CSV row without country → keep the stored value (unchanged semantics).
    db.add(Stock(ticker="SAP", exchange="XETRA", name="SAP SE", country="DE"))
    db.commit()
    seed_service.seed_stocks_no_index_from_csv(
        db, _csv("SAP,XETRA,SAP SE,Technology,,,EUR")
    )
    db.commit()
    stock = db.execute(select(Stock).where(Stock.ticker == "SAP")).scalar_one()
    assert stock.country == "DE"
