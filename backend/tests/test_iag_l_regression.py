"""End-to-end regression guard for IAG.L (and the prev_close override fix
from c506158).

Setup: a Stock with currency='GBP', several OHLCV bars in pounds (post
Plan #2 Phase 3 backfill), mocked yfinance fast_info returning live
price + a wrong previousClose. Expectation: live_quote_service.get_quote
returns prev_close from the OHLCV table, not yfinance's wrong value, AND
the live price is correctly scaled pence->pounds.

Without Phase 2's ingestion scaler + Phase 3's backfill, the OHLCV would
be in pence and prev_close override would return a value off by 100x,
producing a bogus -98% day-over-day "drop" for IAG.L. This test guards
both fixes.
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import live_quote_service


def _seed_iag_in_pounds(db: Session) -> Stock:
    """Seed an IAG.L-shaped stock with OHLCV already in pounds (post-Phase 3
    state). Two daily bars: 3.27 (prior) and 3.30 (most recent)."""
    s = Stock(
        ticker="IAG_TEST.L", exchange="LSE", name="IAG Test",
        sector="Industrials", country="GB", currency="GBP",
    )
    db.add(s); db.commit()
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 6),
                      open=3.20, high=3.30, low=3.18, close=3.27, volume=10_000_000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 7),
                      open=3.27, high=3.35, low=3.25, close=3.30, volume=11_000_000))
    db.commit()
    return s


def _make_fake_yf_ticker(currency: str, last: float, prev: float,
                         day_open: float = 0.0, day_high: float = 0.0,
                         day_low: float = 0.0, last_volume: int = 0) -> MagicMock:
    """Build a MagicMock that mimics yfinance.Ticker.fast_info."""
    fake_fast_info = MagicMock()
    fake_fast_info.get = MagicMock(side_effect=lambda k, *args: {
        "lastPrice":     last,
        "previousClose": prev,
        "currency":      currency,
        "open":          day_open,
        "dayHigh":       day_high,
        "dayLow":        day_low,
        "lastVolume":    last_volume,
    }.get(k, None))
    fake_ticker = MagicMock()
    fake_ticker.fast_info = fake_fast_info
    return fake_ticker


def test_iag_l_prev_close_uses_ohlcv_in_pounds(db: Session, monkeypatch) -> None:
    """yfinance returns lastPrice in pence (332.0 = 3.32 pounds) and a
    wrong previousClose (320.0 pence = 3.20 pounds). The override should
    use OHLCV's most recent close (3.30 pounds) since live is intra-day
    (live_price 3.32 != most_recent_close 3.30 within 0.01 tolerance).
    Day-over-day change comes out as +0.02, not a bogus -98%."""
    _seed_iag_in_pounds(db)
    live_quote_service.clear_cache()

    fake_ticker = _make_fake_yf_ticker(
        currency="GBp",
        last=332.0,            # pence -> 3.32 pounds after scaler
        prev=320.0,            # pence -> 3.20 pounds (ignored if override hits)
        day_open=327.0, day_high=335.0, day_low=325.0, last_volume=10_000_000,
    )

    with patch("yfinance.Ticker", return_value=fake_ticker):
        quote = live_quote_service.get_quote("IAG_TEST.L", force_refresh=True)

    assert quote.error is None, f"unexpected error: {quote.error}"
    # Live price scaled: 332 pence / 100 = 3.32 pounds
    assert quote.price == pytest.approx(3.32, abs=0.01)
    # prev_close from OHLCV override: most-recent bar's close (3.30) since
    # live differs from it by more than $0.01 (intra-day case)
    assert quote.prev_close == pytest.approx(3.30, abs=0.01)
    # Day-over-day change: 3.32 - 3.30 = +0.02 (sane, NOT a -98% disaster)
    assert quote.change_abs == pytest.approx(0.02, abs=0.01)
    assert -10 < quote.change_pct < 10, (
        f"sane change_pct expected, got {quote.change_pct} -- if this is "
        f"~-98% the OHLCV is in pence again (Phase 3 backfill regressed)"
    )
    # Currency is normalized to 'GBP' (not 'GBp') in the output
    assert quote.currency == "GBP"


def test_arm_us_prev_close_uses_ohlcv_when_yfinance_disagrees(db: Session) -> None:
    """Original c506158 case: ARM 2026-05-08 had yfinance previousClose=222.12
    while the actual prior trading day's close was 237.30 (a -10.11% real
    move that yfinance was reporting as -3.97%). The override picks the DB
    value over yfinance.

    Setup: live_price matches the most-recent bar within $0.01 (market-closed
    scenario), so the override goes back ONE bar to find the true prior close.
    """
    s = Stock(
        ticker="ARM_TEST", exchange="NASDAQ", name="ARM Test",
        sector="Technology", country="US", currency="USD",
    )
    db.add(s); db.commit()
    # Two bars: prior (237.30) and most-recent (213.30) -- a -10% real move.
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 7),
                      open=235.0, high=238.0, low=234.0, close=237.30, volume=20_000_000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 8),
                      open=215.0, high=216.0, low=210.0, close=213.30, volume=30_000_000))
    db.commit()

    live_quote_service.clear_cache()

    # Market-closed scenario: yfinance "live price" IS today's close.
    # |live_price - most_recent_close| < 0.01 triggers the "go-back-one" branch.
    fake_ticker = _make_fake_yf_ticker(
        currency="USD",
        last=213.30,
        prev=222.12,           # the WRONG yfinance value
        day_open=215.0, day_high=216.0, day_low=210.0, last_volume=30_000_000,
    )

    with patch("yfinance.Ticker", return_value=fake_ticker):
        quote = live_quote_service.get_quote("ARM_TEST", force_refresh=True)

    assert quote.error is None
    assert quote.price == pytest.approx(213.30, abs=0.01)
    # Override goes back one bar -> prior close 237.30, NOT yfinance's 222.12
    assert quote.prev_close == pytest.approx(237.30, abs=0.01)
    # Real day-over-day: 213.30 - 237.30 = -24.0
    assert quote.change_abs == pytest.approx(-24.0, abs=0.5)
    # -10% real move, NOT -3.97% (yfinance's wrong reading)
    assert -12 < quote.change_pct < -8, (
        f"expected -10% real move, got {quote.change_pct}"
    )


def test_us_ticker_no_pence_scaling_applied(db: Session) -> None:
    """Sanity check: a US ticker (currency=USD) is NOT scaled by /100.
    Guards against an over-zealous future change to _scale_pence_to_pounds
    that would mistakenly catch USD."""
    s = Stock(
        ticker="AAPL_TEST", exchange="NASDAQ", name="Apple Test",
        sector="Technology", country="US", currency="USD",
    )
    db.add(s); db.commit()
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 7),
                      open=180.0, high=182.0, low=179.0, close=180.5, volume=50_000_000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 8),
                      open=180.5, high=183.0, low=180.0, close=181.5, volume=55_000_000))
    db.commit()

    live_quote_service.clear_cache()

    fake_ticker = _make_fake_yf_ticker(
        currency="USD",
        last=181.5,
        prev=180.5,
        day_open=180.5, day_high=183.0, day_low=180.0, last_volume=55_000_000,
    )

    with patch("yfinance.Ticker", return_value=fake_ticker):
        quote = live_quote_service.get_quote("AAPL_TEST", force_refresh=True)

    assert quote.error is None
    # Numbers stay as USD -- no /100 scaling
    assert quote.price == pytest.approx(181.5, abs=0.01)
    assert quote.currency == "USD"
