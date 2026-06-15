"""Live-assets dashboard meta: real-time `is_live` (category-aware) + the
`quote_symbol` that the detail link must match (cash↔futures)."""
from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.market import _globex_session_live, _quote_is_live


def _q(state="OPEN", price=100.0, error=None):
    return SimpleNamespace(market_state=state, price=price, error=error)


def test_globex_open_weekday_midday():
    # Wed 14:00 UTC — Globex trading
    assert _globex_session_live(datetime(2026, 6, 10, 14, 0, tzinfo=UTC)) is True


def test_globex_closed_saturday():
    assert _globex_session_live(datetime(2026, 6, 13, 14, 0, tzinfo=UTC)) is False


def test_globex_closed_daily_break():
    # 21:30 UTC — inside the ~1h maintenance break
    assert _globex_session_live(datetime(2026, 6, 10, 21, 30, tzinfo=UTC)) is False


def test_globex_friday_evening_closed_sunday_reopen():
    assert _globex_session_live(datetime(2026, 6, 12, 23, 0, tzinfo=UTC)) is False  # Fri 23:00
    assert _globex_session_live(datetime(2026, 6, 14, 23, 0, tzinfo=UTC)) is True   # Sun 23:00


def test_crypto_always_live():
    sat = datetime(2026, 6, 13, 3, 0, tzinfo=UTC)
    assert _quote_is_live("crypto", False, _q(state="CLOSED"), sat) is True


def test_index_futures_live_after_cash_close():
    # Cash CLOSED but we're on the Globex session → futures price is live.
    wed_evening = datetime(2026, 6, 10, 1, 0, tzinfo=UTC)
    assert _quote_is_live("index", True, _q(state="CLOSED"), wed_evening) is True


def test_cash_index_live_only_when_open():
    t = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    assert _quote_is_live("index", False, _q(state="OPEN"), t) is True
    assert _quote_is_live("index", False, _q(state="CLOSED"), t) is False


def test_commodity_follows_globex():
    sat = datetime(2026, 6, 13, 14, 0, tzinfo=UTC)
    wed = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
    assert _quote_is_live("commodity", False, _q(state="CLOSED"), wed) is True
    assert _quote_is_live("commodity", False, _q(state="CLOSED"), sat) is False
