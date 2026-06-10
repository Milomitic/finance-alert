"""Regression guards for the second wave of stock-detail bugs.

Two independent bugs, both surfacing on the stock-detail page when the
market is closed:

1. Fundamentals partial-fetch persistence: `_fetch_fresh` swallowed per-
   endpoint failures (income_stmt OK, info FAILED → micro+profile empty).
   The L2 cache then persisted the partial payload with `error=None`,
   making it look like a successful fetch — and the user saw an empty
   "Profilo Società" + empty "Valutazione" card for 24h with no error.
   Fix: detect the partial state on read AND on write so existing rows
   re-fetch and new partials never enter L2.

2. Live quote during market-closed hours: `fast_info.lastPrice` returns
   a post-market drift quote (e.g. MU on 2026-05-09 Saturday returned
   $746.81 against the actual Friday close of $743.82). The UI labels
   this value "ULTIMA CHIUSURA", so showing post-market drift is
   misleading. Worse, the variation +0.40% hid the real Thurs→Fri move
   of +15.03%. Fix: when the market is closed AND OHLCV bars are
   available, source price+prev_close directly from the daily-scan
   table — both labelled and computed values become the true close-to-
   close pair.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import fetch_cache_store, live_quote_service
from app.services.fetch_cache_store import (
    _is_payload_too_partial,
)
from app.services.stock_fundamentals_service import (
    CompanyProfile,
    Fundamentals,
    MicroData,
)


# ─── Fix #1: partial-fetch detection ────────────────────────────────────────

def test_payload_with_empty_info_is_marked_partial() -> None:
    """All-None micro + empty profile = info call failed → partial."""
    payload = {
        "ticker": "MU",
        "annual": [{"fiscal_year_end": "2025-08-31", "revenue": 25e9, "net_income": 8e9, "eps": 7.2}],
        "quarterly": [],
        "earnings": [],
        "micro": {k: None for k in vars(MicroData())},
        "profile": {"long_business_summary": None, "website": None,
                    "employees": None, "city": None, "country": None,
                    "ceo": None, "founded": None},
        "insiders": [],
        "analyst_ratings": [],
        "analyst_actions": [],
    }
    assert _is_payload_too_partial(payload) is True


def test_payload_with_some_micro_data_is_not_partial() -> None:
    """Even one populated micro field counts as 'info call succeeded'."""
    payload = {
        "ticker": "AAPL",
        "micro": {**{k: None for k in vars(MicroData())}, "trailing_pe": 27.5},
        "profile": {"long_business_summary": None, "website": None,
                    "employees": None, "city": None, "country": None,
                    "ceo": None, "founded": None},
    }
    assert _is_payload_too_partial(payload) is False


def test_payload_with_business_summary_is_not_partial() -> None:
    """Profile text alone is enough — info call clearly succeeded."""
    payload = {
        "ticker": "AAPL",
        "micro": {k: None for k in vars(MicroData())},
        "profile": {"long_business_summary": "Apple designs and sells consumer electronics.",
                    "website": None, "employees": None, "city": None,
                    "country": None, "ceo": None, "founded": None},
    }
    assert _is_payload_too_partial(payload) is False


def test_read_fundamentals_treats_partial_as_stale(db: Session) -> None:
    """Regression: a partial L2 row must be skipped on read so the next
    `get_fundamentals` call goes upstream instead of returning empty UI."""
    partial = Fundamentals(
        ticker="MU",
        # Annual + quarterly populated (income_stmt succeeded)
        annual=[],
        quarterly=[],
        earnings=[],
        # Info clearly failed: micro all None, profile empty
        micro=MicroData(),
        profile=CompanyProfile(),
    )
    fetch_cache_store.write_fundamentals(db, partial)
    # Within TTL but partial → must return None to trigger upstream re-fetch
    out = fetch_cache_store.read_fundamentals(db, "MU", max_age_seconds=86400)
    assert out is None


def test_read_fundamentals_returns_full_row(db: Session) -> None:
    """Regression complement: a NON-partial row must still be returned."""
    full = Fundamentals(
        ticker="AAPL",
        micro=MicroData(trailing_pe=27.5, return_on_equity=1.41),
        profile=CompanyProfile(long_business_summary="Apple ..."),
    )
    fetch_cache_store.write_fundamentals(db, full)
    out = fetch_cache_store.read_fundamentals(db, "AAPL", max_age_seconds=86400)
    assert out is not None
    assert out.ticker == "AAPL"
    assert out.micro.trailing_pe == 27.5


def test_hydrate_skips_partial_rows(db: Session) -> None:
    """Startup hydration must also skip partials so a process restart
    doesn't re-prime L1 with the bad data."""
    fetch_cache_store.write_fundamentals(db, Fundamentals(ticker="MU", micro=MicroData(), profile=CompanyProfile()))
    fetch_cache_store.write_fundamentals(db, Fundamentals(ticker="AAPL", micro=MicroData(trailing_pe=27.5)))
    out, skipped = fetch_cache_store.hydrate_all_fundamentals(db, max_age_seconds=86400)
    assert "MU" not in out
    assert "AAPL" in out


def test_fetch_fresh_marks_empty_info_as_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the info endpoint clearly failed (no micro fields, no profile),
    `_fetch_fresh` must set `f.error` so the caller skips the L2 write.
    Otherwise the partial sticks around for 24h, surfacing as an empty UI."""
    import pandas as pd

    from app.services import stock_fundamentals_service

    class FakeTicker:
        """All endpoints return empty/None so micro stays empty MicroData()
        and profile stays empty CompanyProfile() — exactly the partial case."""
        def __init__(self, _t: str) -> None:
            pass
        @property
        def income_stmt(self) -> pd.DataFrame:
            return pd.DataFrame()
        @property
        def quarterly_income_stmt(self) -> pd.DataFrame:
            return pd.DataFrame()
        @property
        def earnings_dates(self) -> pd.DataFrame:
            return pd.DataFrame()
        def get_info(self) -> dict:
            return {}      # <-- info call returns nothing
        @property
        def insider_transactions(self) -> pd.DataFrame:
            return pd.DataFrame()
        @property
        def recommendations(self) -> pd.DataFrame:
            return pd.DataFrame()
        @property
        def analyst_price_targets(self) -> dict:
            return {}
        @property
        def upgrades_downgrades(self) -> pd.DataFrame:
            return pd.DataFrame()

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    f = stock_fundamentals_service._fetch_fresh("MU")
    # Partial detection MUST set error so the caller's
    # `if not fresh.error: write_fundamentals(...)` skips the L2 write.
    assert f.error is not None
    assert "partial" in f.error.lower() or "info" in f.error.lower()


# ─── Fix #2: live quote sources EOD pair from OHLCV when market closed ─────

def _seed_us_stock_with_bars(db: Session, ticker: str = "MU") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
              sector="Technology", country="US")
    db.add(s)
    db.flush()
    # Two recent daily bars: most-recent close vs prior. Mirrors the real
    # MU situation that motivated this fix.
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 8),
                      open=700.0, high=750.0, low=695.0,
                      close=743.82, volume=50_000_000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 7),
                      open=650.0, high=668.0, low=645.0,
                      close=646.63, volume=45_000_000))
    db.commit()
    return s


def test_eod_pair_from_ohlcv_returns_two_most_recent_closes(db: Session) -> None:
    _seed_us_stock_with_bars(db)
    pair = live_quote_service._eod_pair_from_ohlcv("MU")
    assert pair is not None
    most_recent, prior = pair
    assert most_recent == 743.82
    assert prior == 646.63


def test_eod_pair_returns_none_for_unknown_ticker(db: Session) -> None:
    """Unknown ticker → caller falls through to yfinance values."""
    assert live_quote_service._eod_pair_from_ohlcv("ZZZZ_NOPE") is None


def test_eod_pair_returns_none_with_only_one_bar(db: Session) -> None:
    """Single-bar stock → can't compute a D/D pair, fall back."""
    s = Stock(ticker="NEW", exchange="NASDAQ", name="New IPO",
              sector="Technology", country="US")
    db.add(s)
    db.flush()
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 8),
                      open=10.0, high=12.0, low=9.5,
                      close=11.0, volume=100_000))
    db.commit()
    assert live_quote_service._eod_pair_from_ohlcv("NEW") is None


def test_quote_when_market_closed_uses_eod_pair(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: when market is closed AND OHLCV bars exist, the live
    quote must report the actual close-to-close pair, NOT yfinance's
    post-market lastPrice + previousClose.

    Concrete numbers from the MU regression:
      yfinance lastPrice = $746.81 (post-market drift)
      yfinance previousClose = $743.82
      OHLCV bars[0].close = $743.82 (Friday's close)
      OHLCV bars[1].close = $646.63 (Thursday's close)
    Expected: price=$743.82, prev=$646.63, variation=+15.03%.
    """
    _seed_us_stock_with_bars(db, ticker="MU")

    class FakeFastInfo:
        def get(self, key: str, default: object = None) -> object:
            return {
                "lastPrice": 746.81,        # post-market drift
                "previousClose": 743.82,    # yfinance's notion of yday
                "currency": "USD",
            }.get(key, default)

    class FakeTicker:
        def __init__(self, _t: str) -> None:
            self.fast_info = FakeFastInfo()
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    # Force the closed-market branch deterministically. This is the
    # POST-market drift case (NOT pre-market), so disable the pre-market
    # path too — otherwise the test's outcome would depend on the wall
    # clock (it would take the pre-market branch when run 08:00-13:30 UTC).
    monkeypatch.setattr(
        "app.services.live_quote_service._is_market_open",
        lambda *_args, **_kw: False,
    )
    monkeypatch.setattr(
        "app.services.live_quote_service._is_premarket",
        lambda *_args, **_kw: False,
    )
    # Pin OUTSIDE the post-close gap (weekend / pre-open / DB already has
    # today): there the settled EOD pair must always beat the drift quote.
    # The complementary case — session ended TODAY but the DB only has
    # yesterday → fast_info lastPrice serves as today's provisional close —
    # is asserted in test_live_quote_service.py (post-close gap tests).
    monkeypatch.setattr(
        "app.services.live_quote_service._session_ended_today",
        lambda *_args, **_kw: False,
    )
    live_quote_service.clear_cache()
    q = live_quote_service.get_quote("MU")
    assert q.market_state == "CLOSED"
    assert q.price == pytest.approx(743.82)
    assert q.prev_close == pytest.approx(646.63)
    assert q.change_abs is not None
    assert q.change_abs == pytest.approx(97.19, abs=0.01)
    assert q.change_pct == pytest.approx(15.03, abs=0.01)


def test_quote_when_market_open_keeps_live_price(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open-market path is unchanged: live yfinance lastPrice is the price,
    OHLCV-derived prev_close is the baseline. The new EOD-pair logic must
    NOT activate here."""
    _seed_us_stock_with_bars(db, ticker="MU")

    class FakeFastInfo:
        def get(self, key: str, default: object = None) -> object:
            return {
                "lastPrice": 750.50,        # intraday tick
                "previousClose": 743.82,
                "currency": "USD",
            }.get(key, default)

    class FakeTicker:
        def __init__(self, _t: str) -> None:
            self.fast_info = FakeFastInfo()
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(
        "app.services.live_quote_service._is_market_open",
        lambda *_args, **_kw: True,
    )
    live_quote_service.clear_cache()
    q = live_quote_service.get_quote("MU")
    assert q.market_state == "OPEN"
    # Price stays the live tick — the new EOD-pair logic is closed-only.
    assert q.price == pytest.approx(750.50)
    # prev_close still gets the OHLCV override (existing behavior, fixes
    # the "yfinance returned wrong previousClose during sharp moves" bug).
    assert q.prev_close == pytest.approx(743.82)
