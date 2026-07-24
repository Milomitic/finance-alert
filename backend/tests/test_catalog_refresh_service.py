"""Catalog refresh service tests."""
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models import CatalogRefreshLog, Index, Stock, StockIndex
from app.services.catalog_refresh_service import (
    refresh_all,
    refresh_index,
)

SP500_TABLE = pd.DataFrame(
    {
        "Symbol": ["AAPL", "MSFT"],
        "Security": ["Apple Inc.", "Microsoft Corp."],
        "GICS Sector": ["IT", "IT"],
        "GICS Sub-Industry": ["Hardware", "Software"],
    }
)


def test_refresh_index_success(db: Session) -> None:
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=SP500_TABLE):
        result = refresh_index(db, "SP500")
    db.commit()
    assert result.status == "success"
    assert result.stocks_added == 2
    assert db.query(Stock).count() == 2
    idx = db.query(Index).filter_by(code="SP500").one()
    assert db.query(StockIndex).filter_by(index_id=idx.id).count() == 2


def test_refresh_index_failure_logs_error(db: Session) -> None:
    with patch(
        "app.services.catalog_refresh_service._fetch_table", side_effect=RuntimeError("boom")
    ):
        result = refresh_index(db, "SP500")
    db.commit()
    assert result.status == "failed"
    assert "boom" in (result.error_message or "")
    log = db.query(CatalogRefreshLog).filter_by(status="failed").one()
    assert log.index_code == "SP500"


def test_refresh_index_unknown_code_raises(db: Session) -> None:
    with pytest.raises(KeyError):
        refresh_index(db, "DOES_NOT_EXIST")


def test_refresh_all_continues_on_failure(db: Session) -> None:
    def selective(url, table_index):
        if "S%26P_500" in url:
            return SP500_TABLE
        raise RuntimeError("source down")

    with patch("app.services.catalog_refresh_service._fetch_table", side_effect=selective):
        results = refresh_all(db)
    db.commit()
    by_code = {r.index_code: r for r in results}
    assert by_code["SP500"].status == "success"
    assert by_code["NDX"].status == "failed"
    assert db.query(Stock).count() >= 2  # SP500 succeeded


# ─── Wipe guards (incident 2026-07-18) ──────────────────────────────────────
# The Saturday refresh deleted all 101 Nasdaq-100 memberships, added none, and
# logged status="success". Wikipedia had served a page this parser could not
# read; `seen_stock_ids` stayed empty and the stale-membership DELETE removed
# everything not in an empty set. NDX then silently disappeared from Market
# Mood and from every breadth average computed over it.


def test_empty_source_does_not_wipe_the_index(db: Session) -> None:
    """THE regression test: an unparseable source must leave membership alone."""
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=SP500_TABLE):
        refresh_index(db, "SP500")
    db.commit()
    idx = db.query(Index).filter_by(code="SP500").one()
    assert db.query(StockIndex).filter_by(index_id=idx.id).count() == 2

    # Same shape Wikipedia returned on 18 July: right columns, no usable rows.
    empty = pd.DataFrame(
        {"Symbol": [], "Security": [], "GICS Sector": [], "GICS Sub-Industry": []}
    )
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=empty):
        result = refresh_index(db, "SP500")
    db.commit()

    assert result.status == "failed", "an empty parse must not report success"
    assert result.stocks_removed == 0
    assert db.query(StockIndex).filter_by(index_id=idx.id).count() == 2, (
        "the index was wiped by an empty source"
    )


def test_drastically_smaller_source_is_refused_as_a_parse_regression(db: Session) -> None:
    """Losing over half the constituents in one run means we are reading the
    wrong table, not that the index was reshuffled."""
    big = pd.DataFrame(
        {
            "Symbol": [f"T{i}" for i in range(10)],
            "Security": [f"Co {i}" for i in range(10)],
            "GICS Sector": ["IT"] * 10,
            "GICS Sub-Industry": ["Software"] * 10,
        }
    )
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=big):
        refresh_index(db, "SP500")
    db.commit()
    idx = db.query(Index).filter_by(code="SP500").one()
    assert db.query(StockIndex).filter_by(index_id=idx.id).count() == 10

    shrunk = big.head(2)   # 2 of 10 — below the retained-ratio floor
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=shrunk):
        result = refresh_index(db, "SP500")
    db.commit()

    assert result.status == "failed"
    assert db.query(StockIndex).filter_by(index_id=idx.id).count() == 10


def test_a_normal_prune_still_goes_through(db: Session) -> None:
    """The guards must not block a real, modest reshuffle."""
    big = pd.DataFrame(
        {
            "Symbol": [f"T{i}" for i in range(10)],
            "Security": [f"Co {i}" for i in range(10)],
            "GICS Sector": ["IT"] * 10,
            "GICS Sub-Industry": ["Software"] * 10,
        }
    )
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=big):
        refresh_index(db, "SP500")
    db.commit()
    idx = db.query(Index).filter_by(code="SP500").one()

    with patch("app.services.catalog_refresh_service._fetch_table", return_value=big.head(8)):
        result = refresh_index(db, "SP500")
    db.commit()

    assert result.status == "success"
    assert result.stocks_removed == 2
    assert db.query(StockIndex).filter_by(index_id=idx.id).count() == 8
