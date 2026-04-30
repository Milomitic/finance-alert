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
