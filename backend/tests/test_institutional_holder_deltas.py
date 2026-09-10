"""A stock holder exposes share and portfolio-weight changes as distinct units."""
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Institutional, InstitutionalFiling, InstitutionalHolding
from app.schemas.institutional import TickerHolderOut
from app.services import institutional_service


def _filing(
    db: Session,
    institutional: Institutional,
    period_end: date,
    *,
    shares: int,
    portfolio_pct: float,
    shares_change_pct: float | None,
) -> None:
    filing = InstitutionalFiling(
        institutional_id=institutional.id,
        period_end_date=period_end,
    )
    db.add(filing)
    db.flush()
    db.add(
        InstitutionalHolding(
            filing_id=filing.id,
            ticker="DG",
            company_name="Dollar General",
            shares=shares,
            value_usd=shares * 100,
            portfolio_pct=portfolio_pct,
            qoq_change_pct=shares_change_pct,
            action="add",
        )
    )
    db.flush()


def test_holder_keeps_share_change_separate_from_weight_delta(db: Session) -> None:
    fund = Institutional(
        slug="unit-fund",
        name="Unit Fund",
        type="institutional",
        source="sec_13f",
    )
    db.add(fund)
    db.flush()

    latest = date.today() - timedelta(days=30)
    _filing(
        db,
        fund,
        latest - timedelta(days=90),
        shares=100,
        portfolio_pct=1.5,
        shares_change_pct=None,
    )
    _filing(
        db,
        fund,
        latest,
        shares=120,
        portfolio_pct=2.0,
        shares_change_pct=20.0,
    )

    [holder] = institutional_service.holders_for_ticker(db, "DG")

    assert holder.shares_change_pct == pytest.approx(20.0)
    assert holder.portfolio_weight_delta_pp == pytest.approx(0.5)
    assert abs(holder.portfolio_weight_delta_pp) <= 100
    payload = TickerHolderOut.model_validate(holder).model_dump()
    assert payload["shares_change_pct"] == pytest.approx(20.0)
    assert payload["portfolio_weight_delta_pp"] == pytest.approx(0.5)
    assert "qoq_change_pct" not in payload


def test_holder_does_not_invent_weight_delta_without_previous_weight(db: Session) -> None:
    fund = Institutional(
        slug="single-filing-fund",
        name="Single Filing Fund",
        type="institutional",
        source="sec_13f",
    )
    db.add(fund)
    db.flush()
    _filing(
        db,
        fund,
        date.today() - timedelta(days=30),
        shares=120,
        portfolio_pct=2.0,
        shares_change_pct=None,
    )

    [holder] = institutional_service.holders_for_ticker(db, "DG")

    assert holder.shares_change_pct is None
    assert holder.portfolio_weight_delta_pp is None


def test_weight_delta_does_not_skip_a_consecutive_filing_without_the_ticker(
    db: Session,
) -> None:
    fund = Institutional(
        slug="reentry-fund",
        name="Re-entry Fund",
        type="institutional",
        source="sec_13f",
    )
    db.add(fund)
    db.flush()
    latest = date.today() - timedelta(days=30)
    _filing(
        db,
        fund,
        latest - timedelta(days=180),
        shares=100,
        portfolio_pct=1.0,
        shares_change_pct=None,
    )
    middle = InstitutionalFiling(
        institutional_id=fund.id,
        period_end_date=latest - timedelta(days=90),
    )
    db.add(middle)
    db.flush()
    db.add(
        InstitutionalHolding(
            filing_id=middle.id,
            ticker="MSFT",
            shares=10,
            value_usd=1_000,
            portfolio_pct=0.5,
        )
    )
    _filing(
        db,
        fund,
        latest,
        shares=50,
        portfolio_pct=2.0,
        shares_change_pct=None,
    )

    [holder] = institutional_service.holders_for_ticker(db, "DG")

    assert holder.portfolio_weight_delta_pp is None
