"""Twelve Data — TIER-3 EPS-actual fallback behind yfinance + Finnhub.

Guards two things:
1. The TD client (`twelvedata_earnings_service`) parses the /earnings
   payload, maps the AMC/BMO `time`, filters released-in-window, and
   fails closed (returns {}/[]) on the TD error envelope.
2. The integration: when Finnhub yields nothing (its breaker open /
   rate-limited), `_merge_finnhub_actuals_into_earnings` reaches into
   Twelve Data and patches the actual — the whole point of adding a
   second, independent free provider.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.services import twelvedata_earnings_service as td
from app.services.stock_fundamentals_service import (
    Fundamentals,
    _merge_finnhub_actuals_into_earnings,
)


def _fake_response(status_code: int, json_body: object) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json = MagicMock(return_value=json_body)
    return r


def _earnings_body(rows: list[dict]) -> dict:
    return {"meta": {"symbol": "AAPL"}, "earnings": rows}


def setup_function() -> None:
    """Each test starts from a clean rate-limiter + closed breaker so
    ordering can't bleed state between cases."""
    td._RATE_TIMESTAMPS.clear()
    td._BLOCKED_UNTIL = None


# ─── client parsing ──────────────────────────────────────────────────

def test_fetch_symbol_earnings_parses_and_maps_hour() -> None:
    body = _earnings_body([
        {"date": "2026-05-01", "time": "After Market",
         "eps_estimate": 2.10, "eps_actual": 2.34},
        {"date": "2026-02-01", "time": "Before Market",
         "eps_estimate": 1.50, "eps_actual": 1.61},
    ])
    with patch.object(td.settings, "twelvedata_api_key", "KEY"), \
         patch("requests.get", return_value=_fake_response(200, body)):
        rows = td.fetch_symbol_earnings("AAPL")
    assert len(rows) == 2
    assert rows[0].date == date(2026, 5, 1)
    assert rows[0].eps_actual == 2.34
    assert rows[0].hour == "amc"
    assert rows[1].hour == "bmo"
    # Free tier has no revenue — always None.
    assert rows[0].revenue_actual is None and rows[0].revenue_estimate is None


def test_fetch_symbol_earnings_fails_closed_on_td_error_envelope() -> None:
    """TD signals errors with a 200 + {status: error} body, not an HTTP
    code. Must return [] (caller falls through), not raise."""
    err = {"code": 404, "message": "symbol not found", "status": "error"}
    with patch.object(td.settings, "twelvedata_api_key", "KEY"), \
         patch("requests.get", return_value=_fake_response(200, err)):
        assert td.fetch_symbol_earnings("NOPE") == []


def test_fetch_recent_actuals_filters_released_in_window() -> None:
    today = date.today()
    body = _earnings_body([
        # Released yesterday — in window, should win.
        {"date": (today - timedelta(days=1)).isoformat(),
         "time": "After Market", "eps_estimate": 2.0, "eps_actual": 2.2},
        # Released long ago — outside the 14d window.
        {"date": (today - timedelta(days=90)).isoformat(),
         "time": "After Market", "eps_estimate": 1.0, "eps_actual": 1.1},
        # Upcoming, no actual yet — must be ignored.
        {"date": (today + timedelta(days=20)).isoformat(),
         "time": "After Market", "eps_estimate": 2.5, "eps_actual": None},
    ])
    with patch.object(td.settings, "twelvedata_api_key", "KEY"), \
         patch("requests.get", return_value=_fake_response(200, body)):
        out = td.fetch_recent_actuals(["AAPL"], days_back=14)
    assert "AAPL" in out
    assert out["AAPL"].eps_actual == 2.2


def test_disabled_when_no_key() -> None:
    with patch.object(td.settings, "twelvedata_api_key", ""):
        assert td.is_enabled() is False
        assert td.fetch_symbol_earnings("AAPL") == []
        assert td.fetch_recent_actuals(["AAPL"]) == {}


def test_breaker_opens_on_429() -> None:
    with patch.object(td.settings, "twelvedata_api_key", "KEY"), \
         patch("requests.get", return_value=_fake_response(429, {})):
        assert td.fetch_symbol_earnings("AAPL") == []
    blocked, _ = td._is_blocked()
    assert blocked is True
    td._BLOCKED_UNTIL = None  # cleanup so we don't persist into other tests


# ─── integration: Finnhub-empty → Twelve Data patches the actual ─────

def test_td_patches_actual_when_finnhub_empty() -> None:
    """yfinance left a past-dated forward event with no actual; Finnhub
    returns nothing (breaker open); Twelve Data fills it in."""
    yesterday = (date.today() - timedelta(days=1))
    f = Fundamentals(ticker="AAPL")
    f.earnings = []
    f.next_earnings_date = yesterday.isoformat()  # past-dated → lagging actual
    f.next_eps_estimate = 2.0

    td_rec = td.TwelveDataEarning(
        symbol="AAPL", date=yesterday,
        eps_actual=2.31, eps_estimate=2.10,
        revenue_actual=None, revenue_estimate=None,
        quarter=None, year=yesterday.year, hour="amc",
    )

    with patch(
        "app.services.finnhub_earnings_service.is_enabled", return_value=True
    ), patch(
        "app.services.finnhub_earnings_service.fetch_recent_actuals",
        return_value={},  # Finnhub has nothing (e.g. breaker open)
    ), patch(
        "app.services.twelvedata_earnings_service.is_enabled", return_value=True
    ), patch(
        "app.services.twelvedata_earnings_service.fetch_recent_actuals",
        return_value={"AAPL": td_rec},
    ):
        _merge_finnhub_actuals_into_earnings("AAPL", f)

    # The actual got patched in from Twelve Data...
    assert len(f.earnings) == 1
    ep = f.earnings[0]
    assert ep.eps_reported == 2.31
    assert ep.eps_estimate == 2.10
    # surprise% = (2.31 - 2.10) / |2.10| * 100 ≈ 10.0
    assert ep.surprise_pct is not None and 9.0 < ep.surprise_pct < 11.0
    # ...and the "upcoming" slot was demoted now that it's historical.
    assert f.next_earnings_date is None
