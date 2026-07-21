"""Position P&L → USD conversion (portfolio-rollup FX)."""
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Position, Stock
from app.services import fx_service, position_service


@pytest.fixture(autouse=True)
def _force_fallback_fx(monkeypatch: pytest.MonkeyPatch):
    """Deterministic FX: no live fetch → hardcoded FX_RATES_FALLBACK
    (EUR 1.10, GBP 1.27, USD 1.0)."""
    monkeypatch.setattr(fx_service, "_fetch_live_rate", lambda cur: None)
    fx_service.clear_cache()


def _pos(db: Session, *, currency: str, ticker: str, entry: float, size: float) -> None:
    stock = Stock(ticker=ticker, exchange="TST", name=ticker, currency=currency)
    db.add(stock)
    db.flush()
    db.add(
        Position(
            stock_id=stock.id, side="long", entry_price=entry, size=size,
            opened_at=datetime.now(UTC),
        )
    )
    db.commit()


def test_open_pnl_and_cost_converted_to_usd(db: Session):
    _pos(db, currency="EUR", ticker="ENEL.MI", entry=10.0, size=100)
    row = position_service.list_positions(db, "open", price_fn=lambda t: 12.0)[0]
    assert row["currency"] == "EUR"
    assert row["unrealized_abs"] == pytest.approx(200.0)  # (12-10)*100 EUR
    assert row["unrealized_usd"] == pytest.approx(220.0)  # ×1.10
    assert row["cost_usd"] == pytest.approx(1100.0)  # 10*100 ×1.10


def test_usd_position_unchanged(db: Session):
    _pos(db, currency="USD", ticker="AAPL", entry=100.0, size=5)
    row = position_service.list_positions(db, "open", price_fn=lambda t: 110.0)[0]
    assert row["unrealized_abs"] == pytest.approx(50.0)
    assert row["unrealized_usd"] == pytest.approx(50.0)  # USD → USD


def test_minor_unit_gbp_normalized(db: Session):
    # A residual 'GBp' currency must convert as GBP — prices are major units.
    _pos(db, currency="GBp", ticker="X.L", entry=5.0, size=10)
    row = position_service.list_positions(db, "open", price_fn=lambda t: 6.0)[0]
    assert row["currency"] == "GBp"
    assert row["unrealized_usd"] == pytest.approx(12.7)  # (6-5)*10 ×1.27, not ×0.0127
