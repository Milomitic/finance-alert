"""An unresolvable currency is UNKNOWN, and a closed trade's USD result is fixed.

Two defects, and measuring production separated them — which reversed their
urgency relative to how the audit ranked them.

**Parity for an unknown currency is LATENT.** `_get_rate` ended
`FX_RATES_FALLBACK.get(cur, 1.0)`, so a currency absent from the table
converted 1:1 and 100 units of anything became 100 USD. Every currency in the
live catalogue — USD, GBP, EUR, HKD, JPY, KRW, GBp, NOK, AUD, DKK — IS in that
table, and no stock has a null currency, so nothing is being corrupted today.
It is a trap for the next listing the catalogue picks up, not a live wrong
number. Note the distinction it must not destroy: for a KNOWN currency whose
live fetch fails, the hardcoded approximation is a deliberate, documented
degradation and stays.

**Converting a closed trade at TODAY's rate is live.** `realized_usd` called
`to_usd` at read time, so the realised result of a position closed months ago
moved every time the exchange rate did. Both of the two positions in
production are on non-USD stocks. A realised number is history: it stops
moving when the trade closes.
"""

from datetime import UTC, datetime

import pytest

from app.models import Position, Stock
from app.services import fx_service, position_service


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    """No live FX in tests; the hardcoded table is the resolver under test."""
    monkeypatch.setattr(fx_service, "_fetch_live_rate", lambda _c: None)
    fx_service.clear_cache()
    yield
    fx_service.clear_cache()


class TestAnUnknownCurrencyIsNotParity:
    def test_it_returns_unknown_rather_than_converting_one_to_one(self):
        assert fx_service.to_usd(100.0, "ZZZ") is None

    def test_a_missing_currency_is_also_unknown(self):
        # Assuming USD because the field is empty is a guess presented as a
        # fact. No stock in the catalogue has one, so nothing is lost by
        # refusing.
        assert fx_service.to_usd(100.0, None) is None
        assert fx_service.to_usd(100.0, "  ") is None

    def test_a_KNOWN_currency_still_falls_back_to_the_table(self):
        # The part that must NOT change: a live-fetch failure on a currency we
        # have an approximation for is a documented degradation, not an
        # unknown. Every currency in the live catalogue lands here.
        assert fx_service.to_usd(100.0, "EUR") == pytest.approx(
            100.0 * fx_service.FX_RATES_FALLBACK["EUR"]
        )

    def test_usd_is_unaffected(self):
        assert fx_service.to_usd(100.0, "USD") == 100.0

    def test_a_none_amount_is_still_none(self):
        assert fx_service.to_usd(None, "EUR") is None

    def test_rate_for_reports_the_rate_or_none(self):
        assert fx_service.rate_for("USD") == 1.0
        assert fx_service.rate_for("EUR") == pytest.approx(
            fx_service.FX_RATES_FALLBACK["EUR"]
        )
        assert fx_service.rate_for("ZZZ") is None


def _stock(db, currency: str = "EUR") -> Stock:
    s = Stock(ticker=f"FX{currency}", exchange="XETRA", name="t", currency=currency)
    db.add(s)
    db.commit()
    return s


class TestTheRateBook:
    def test_opening_stamps_the_rate_of_the_day(self, db):
        s = _stock(db)
        pos = position_service.open_position(db, stock_id=s.id, entry_price=100.0, size=10)

        assert float(pos.entry_fx_rate) == pytest.approx(
            fx_service.FX_RATES_FALLBACK["EUR"]
        )

    def test_closing_stamps_the_rate_at_close(self, db):
        s = _stock(db)
        pos = position_service.open_position(db, stock_id=s.id, entry_price=100.0, size=10)
        closed = position_service.close_position(db, pos.id, exit_price=110.0)

        assert closed.exit_fx_rate is not None

    def test_a_closed_position_keeps_its_usd_result_when_the_rate_moves(self, db, monkeypatch):
        s = _stock(db)
        pos = position_service.open_position(db, stock_id=s.id, entry_price=100.0, size=10)
        position_service.close_position(db, pos.id, exit_price=110.0)

        before = position_service.list_positions(db, status="closed")[0]["realized_usd"]

        # The euro doubles overnight. A trade closed yesterday did not.
        monkeypatch.setattr(fx_service, "_fetch_live_rate", lambda _c: 2.0)
        fx_service.clear_cache()
        after = position_service.list_positions(db, status="closed")[0]["realized_usd"]

        assert after == pytest.approx(before)

    def test_an_OPEN_position_still_marks_to_the_current_rate(self, db, monkeypatch):
        # Unrealised is a mark-to-market: it SHOULD move with the rate. Only
        # the realised leg is history.
        s = _stock(db)
        position_service.open_position(db, stock_id=s.id, entry_price=100.0, size=10)

        monkeypatch.setattr(fx_service, "_fetch_live_rate", lambda _c: 2.0)
        fx_service.clear_cache()
        row = position_service.list_positions(db, status="open")[0]

        assert row["cost_usd"] == pytest.approx(100.0 * 10 * 2.0)

    def test_a_position_predating_the_rate_book_falls_back_to_the_current_rate(self, db):
        # Existing rows have no stamped rate. Converting them at today's rate
        # is what already happened to them; refusing would blank a number the
        # user has been reading.
        s = _stock(db)
        db.add(
            Position(
                stock_id=s.id, side="long", entry_price=100.0, size=10,
                closed_at=datetime.now(UTC), exit_price=110.0, exit_reason="manual",
            )
        )
        db.commit()

        row = position_service.list_positions(db, status="closed")[0]

        assert row["realized_usd"] == pytest.approx(
            100.0 * fx_service.FX_RATES_FALLBACK["EUR"]
        )
