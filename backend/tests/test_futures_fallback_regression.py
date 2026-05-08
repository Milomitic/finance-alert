"""Regression-guard tests for commit df5ff78.

Bug: when a US cash market index (e.g. ^GSPC) is closed (weekend / overnight),
the live-assets dashboard panel was showing stale EOD values. The fix in
df5ff78 introduces a futures fallback inside the GET /api/dashboard/live-assets
route handler in `backend/app/api/market.py`:

    cash market_state == "OPEN"           -> serve cash quote
    cash CLOSED + futures has price       -> serve futures quote, using_futures=True
    cash CLOSED + no futures pair / err   -> fall through to cash (frozen)

These tests exercise the route handler with `live_quote_service.get_quotes_batch`
and `live_sparkline_service.get_sparklines` mocked, and assert the swap logic
holds for ^GSPC ↔ ES=F. They MUST NOT touch production code.
"""
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.services.live_quote_service import LiveQuote


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_quote(
    ticker: str,
    price: float | None,
    market_state: str | None,
    *,
    error: str | None = None,
) -> LiveQuote:
    """Build a LiveQuote with just the fields the swap logic reads."""
    return LiveQuote(
        ticker=ticker,
        price=price,
        prev_close=price,
        change_abs=0.0,
        change_pct=0.0,
        market_state=market_state,
        fetched_at=1.0,
        error=error,
    )


def _build_batch_stub(quotes_by_symbol: dict[str, LiveQuote]):
    """Returns a fn matching live_quote_service.get_quotes_batch signature.

    For tickers we don't care about (other indices, commodities, crypto) we
    return a benign closed quote so the route still produces a row without
    triggering the swap branch we're not testing.
    """
    def _stub(tickers: list[str]) -> dict[str, LiveQuote]:
        out: dict[str, LiveQuote] = {}
        for t in tickers:
            if t in quotes_by_symbol:
                out[t] = quotes_by_symbol[t]
            else:
                # Default: closed cash quote with a price. For a futures
                # symbol we don't explicitly mock, return None price so
                # the swap WON'T happen for that row (futures price is
                # required to be not None).
                if t.endswith("=F") and t not in ("GC=F", "SI=F", "CL=F", "NG=F"):
                    out[t] = _make_quote(t, None, "CLOSED", error="not mocked")
                else:
                    out[t] = _make_quote(t, 100.0, "CLOSED")
        return out
    return _stub


def _spx_row(payload: dict) -> dict:
    """Extract the ^GSPC row from /api/dashboard/live-assets response."""
    rows = [a for a in payload["assets"] if a["symbol"] == "^GSPC"]
    assert len(rows) == 1, f"expected one ^GSPC row, got {rows}"
    return rows[0]


def test_futures_quote_used_when_cash_market_closed(client):
    """Cash CLOSED + futures has a valid price -> use futures, set using_futures=True."""
    cash_price = 5800.0   # stale EOD close
    futures_price = 7408.0  # fresh after-hours futures
    quotes = {
        "^GSPC": _make_quote("^GSPC", cash_price, "CLOSED"),
        "ES=F": _make_quote("ES=F", futures_price, "CLOSED"),
    }
    with patch(
        "app.api.market.live_quote_service.get_quotes_batch",
        side_effect=_build_batch_stub(quotes),
    ), patch(
        "app.api.market.live_sparkline_service.get_sparklines",
        return_value={},
    ):
        resp = client.get("/api/dashboard/live-assets")

    assert resp.status_code == 200, resp.text
    spx = _spx_row(resp.json())
    assert spx["using_futures"] is True, (
        f"^GSPC should have using_futures=True when cash is CLOSED and ES=F has a price; "
        f"row={spx}"
    )
    assert spx["quote"]["price"] == futures_price, (
        f"^GSPC price should be the futures price ({futures_price}), not cash ({cash_price}); "
        f"got {spx['quote']['price']}"
    )


def test_cash_quote_used_when_market_open(client):
    """Cash OPEN -> use cash regardless of futures, using_futures=False."""
    cash_price = 5800.0
    futures_price = 7408.0
    quotes = {
        "^GSPC": _make_quote("^GSPC", cash_price, "OPEN"),
        "ES=F": _make_quote("ES=F", futures_price, "CLOSED"),
    }
    with patch(
        "app.api.market.live_quote_service.get_quotes_batch",
        side_effect=_build_batch_stub(quotes),
    ), patch(
        "app.api.market.live_sparkline_service.get_sparklines",
        return_value={},
    ):
        resp = client.get("/api/dashboard/live-assets")

    assert resp.status_code == 200, resp.text
    spx = _spx_row(resp.json())
    assert spx["using_futures"] is False, (
        f"^GSPC should have using_futures=False when cash market is OPEN; row={spx}"
    )
    assert spx["quote"]["price"] == cash_price, (
        f"^GSPC price should be the cash price ({cash_price}) when market is OPEN; "
        f"got {spx['quote']['price']}"
    )


def test_falls_back_to_cash_when_futures_unavailable(client):
    """Cash CLOSED + futures fetch errored / has no price -> serve cash, no crash."""
    cash_price = 5800.0
    quotes = {
        "^GSPC": _make_quote("^GSPC", cash_price, "CLOSED"),
        # Futures quote present but with error and price=None — simulates a
        # failed yfinance fetch for ES=F.
        "ES=F": _make_quote("ES=F", None, "CLOSED", error="upstream timeout"),
    }
    with patch(
        "app.api.market.live_quote_service.get_quotes_batch",
        side_effect=_build_batch_stub(quotes),
    ), patch(
        "app.api.market.live_sparkline_service.get_sparklines",
        return_value={},
    ):
        resp = client.get("/api/dashboard/live-assets")

    assert resp.status_code == 200, resp.text
    spx = _spx_row(resp.json())
    assert spx["using_futures"] is False, (
        f"^GSPC should fall back to cash when futures is unavailable; row={spx}"
    )
    assert spx["quote"] is not None, "cash quote should still be served"
    assert spx["quote"]["price"] == cash_price, (
        f"^GSPC should serve the cash price ({cash_price}) as best-effort fallback; "
        f"got {spx['quote']['price']}"
    )
