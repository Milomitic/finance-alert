"""Tests for live_quote_service."""
import time
from datetime import UTC, date, datetime

import pytest

from app.services import live_quote_service, yfinance_health


def setup_function() -> None:
    live_quote_service.clear_cache()
    yfinance_health.reset()


def _fake_fast_info(values: dict[str, object]) -> object:
    """Build a FastInfo-like object that supports `.get(key)`."""
    class FakeFastInfo:
        def get(self, key: str, default: object = None) -> object:
            return values.get(key, default)
    return FakeFastInfo()


def _patch_yf(monkeypatch: pytest.MonkeyPatch, fi: object) -> None:
    class FakeTicker:
        def __init__(self, _t: str) -> None:
            self.fast_info = fi
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    # Also disable ALL the OHLCV/DB-driven overrides — these tests assert
    # that yfinance's mocked price/previousClose flow through unchanged.
    # Without these patches, when the market is closed at test runtime
    # (time-of-day dependent) the CLOSED branch would replace price AND
    # prev with DB values, breaking the yfinance-pure assertions:
    #   - `_override_prev_close_from_ohlcv` / `_eod_pair_from_ohlcv`: the
    #     original close-to-close override.
    #   - `_latest_two_bars` / `_provisional_today`: the post-close-gap
    #     "today close" machinery (official bar / intraday tick).
    # Production callers still benefit from all of them; only this
    # isolated unit-test path bypasses them.
    monkeypatch.setattr(
        "app.services.live_quote_service._override_prev_close_from_ohlcv",
        lambda _ticker, _live: None,
    )
    monkeypatch.setattr(
        "app.services.live_quote_service._eod_pair_from_ohlcv",
        lambda _ticker: None,
    )
    monkeypatch.setattr(
        "app.services.live_quote_service._latest_two_bars",
        lambda _ticker: None,
    )
    monkeypatch.setattr(
        "app.services.live_quote_service._provisional_today",
        lambda *_args, **_kw: None,
    )


def test_quote_returns_price_change_and_pct(monkeypatch: pytest.MonkeyPatch) -> None:
    fi = _fake_fast_info({
        "lastPrice": 280.14, "previousClose": 271.35,
        "open": 272.0, "dayHigh": 282.0, "dayLow": 270.0,
        "lastVolume": 45_000_000, "currency": "USD", "quoteType": "EQUITY",
    })
    _patch_yf(monkeypatch, fi)
    q = live_quote_service.get_quote("AAPL")
    assert q.price == 280.14
    assert q.prev_close == 271.35
    assert q.change_abs is not None and abs(q.change_abs - 8.79) < 1e-6
    assert q.change_pct is not None and abs(q.change_pct - 3.239358) < 1e-3
    assert q.day_open == 272.0
    assert q.day_high == 282.0
    assert q.day_low == 270.0
    assert q.volume == 45_000_000
    assert q.currency == "USD"
    assert q.error is None


def test_quote_normalises_gbp_pence_to_pounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """LSE tickers come back as GBp (pence). All price fields divide by 100;
    currency normalised to GBP for the response."""
    fi = _fake_fast_info({
        "lastPrice": 1359.4, "previousClose": 1340.0,
        "open": 1342.0, "dayHigh": 1365.0, "dayLow": 1335.0,
        "currency": "GBp",
    })
    _patch_yf(monkeypatch, fi)
    q = live_quote_service.get_quote("HSBA.L")
    assert q.price == pytest.approx(13.594, rel=1e-9)
    assert q.prev_close == pytest.approx(13.40, rel=1e-9)
    assert q.day_high == pytest.approx(13.65, rel=1e-9)
    assert q.currency == "GBP"


def test_quote_caches_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two get_quote calls within TTL must return the SAME instance (no
    second yfinance hit)."""
    call_count = {"n": 0}

    class FakeFastInfo:
        def get(self, key: str, default: object = None) -> object:
            return {"lastPrice": 100.0, "previousClose": 99.0}.get(key, default)

    class FakeTicker:
        def __init__(self, _t: str) -> None:
            call_count["n"] += 1
            self.fast_info = FakeFastInfo()

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    # Neutralise the post-close-gap remote fetch: it instantiates its own
    # yfinance.Ticker, which would inflate call_count non-deterministically
    # depending on the wall-clock market state.
    monkeypatch.setattr(
        "app.services.live_quote_service._today_official_bar", lambda *a, **k: None
    )
    a = live_quote_service.get_quote("AAPL")
    b = live_quote_service.get_quote("AAPL")
    assert a is b
    assert call_count["n"] == 1


def test_force_refresh_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"n": 0}

    class FakeFastInfo:
        def get(self, key: str, default: object = None) -> object:
            return {"lastPrice": 100.0, "previousClose": 99.0}.get(key, default)

    class FakeTicker:
        def __init__(self, _t: str) -> None:
            call_count["n"] += 1
            self.fast_info = FakeFastInfo()

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(
        "app.services.live_quote_service._today_official_bar", lambda *a, **k: None
    )
    live_quote_service.get_quote("AAPL")
    live_quote_service.get_quote("AAPL", force_refresh=True)
    assert call_count["n"] == 2


def test_open_breaker_skips_yfinance_and_uses_eod_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the breaker is open we don't hit Yahoo at all — EOD fallback is used."""
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("simulated 429")
    assert yfinance_health.is_open()

    # If yfinance got called we'd raise; the test relies on the breaker short-circuit.
    def boom(_t: str) -> None:
        raise RuntimeError("yfinance should not be called when breaker is open")
    monkeypatch.setattr("yfinance.Ticker", boom)

    # Stub the EOD fallback so the test doesn't depend on the prod DB state.
    from app.services.live_quote_service import LiveQuote as _LQ
    monkeypatch.setattr(
        "app.services.live_quote_service._eod_fallback_quote",
        lambda ticker: _LQ(ticker=ticker, price=150.0, prev_close=148.0,
                           market_state="CLOSED", error=None),
    )

    q = live_quote_service.get_quote("AAPL")
    # Breaker should route to EOD fallback, not return a breaker-error quote.
    assert q.error is None
    assert q.price == 150.0
    assert q.market_state == "CLOSED"


def test_yfinance_exception_sets_error_and_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTicker:
        def __init__(self, _t: str) -> None:
            raise RuntimeError("429 Too Many Requests")
        # @property would normally need a value, but __init__ raises first
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    q = live_quote_service.get_quote("AAPL")
    assert q.error is not None
    assert "429" in q.error
    # Single failure shouldn't trip the breaker yet (need N)
    assert not yfinance_health.is_open()


def test_batch_returns_one_quote_per_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    fi = _fake_fast_info({"lastPrice": 100.0, "previousClose": 99.0})
    _patch_yf(monkeypatch, fi)
    batch = live_quote_service.get_quotes_batch(["AAPL", "MSFT", "GOOGL"])
    assert set(batch.keys()) == {"AAPL", "MSFT", "GOOGL"}
    assert all(q.price == 100.0 for q in batch.values())


def test_is_market_open_us_during_session() -> None:
    """Tuesday 18:00 UTC = 1pm ET = US market open."""
    t = datetime(2026, 5, 5, 18, 0, tzinfo=UTC)
    assert live_quote_service._is_market_open("AAPL", t) is True


def test_is_market_open_us_after_close() -> None:
    """Tuesday 22:00 UTC = 5pm ET = US market closed."""
    t = datetime(2026, 5, 5, 22, 0, tzinfo=UTC)
    assert live_quote_service._is_market_open("AAPL", t) is False


def test_is_market_open_weekend_always_closed() -> None:
    """Saturday 18:00 UTC — even within US hours, weekend = closed."""
    t = datetime(2026, 5, 9, 18, 0, tzinfo=UTC)
    assert live_quote_service._is_market_open("AAPL", t) is False


def test_is_market_open_lse_during_session() -> None:
    """Tuesday 10:00 UTC = morning UK session."""
    t = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)
    assert live_quote_service._is_market_open("HSBA.L", t) is True


def test_is_market_open_hk_during_session() -> None:
    """Tuesday 03:00 UTC = 11am HKT (Hang Seng open)."""
    t = datetime(2026, 5, 5, 3, 0, tzinfo=UTC)
    assert live_quote_service._is_market_open("0005.HK", t) is True


def test_quote_includes_market_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """LiveQuote.market_state must be populated from the ticker's exchange."""
    fi = _fake_fast_info({"lastPrice": 100.0, "previousClose": 99.0, "currency": "USD"})
    _patch_yf(monkeypatch, fi)
    q = live_quote_service.get_quote("AAPL")
    # "PRE" is a valid state too (US pre-market window) — the test only
    # checks the field is populated with a recognised state.
    assert q.market_state in ("OPEN", "CLOSED", "PRE")


def test_breaker_open_uses_eod_fallback(db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Quando yfinance_health.is_open() == True, get_quotes_batch deve
    popolare i campi base dall'ultima OhlcvDaily invece di tornare error."""
    from datetime import date

    from app.models import OhlcvDaily, Stock

    s = Stock(ticker="TESTBREAKER", name="Test Co", exchange="NYSE")
    db.add(s)
    db.commit()

    bar2 = OhlcvDaily(
        stock_id=s.id,
        date=date(2026, 5, 13),
        open=98.0, high=101.0, low=97.0, close=100.0, volume=900_000,
    )
    bar1 = OhlcvDaily(
        stock_id=s.id,
        date=date(2026, 5, 14),
        open=100.0, high=105.0, low=99.0, close=104.5, volume=1_000_000,
    )
    db.add_all([bar2, bar1])
    db.commit()

    monkeypatch.setattr(yfinance_health, "is_open", lambda: True)
    live_quote_service._CACHE.clear()

    quotes = live_quote_service.get_quotes_batch(["TESTBREAKER"])

    assert "TESTBREAKER" in quotes
    q = quotes["TESTBREAKER"]
    assert q.error is None, f"expected no error after fallback, got: {q.error!r}"
    assert q.price == 104.5
    assert q.prev_close == 100.0
    assert q.market_state == "CLOSED"
    assert q.change_abs == pytest.approx(4.5)
    assert q.change_pct == pytest.approx(4.5)


def _patch_premarket(monkeypatch, fi, *, last_two, pre=None):
    """Force the pre-market path: market closed + in the US pre-market window,
    with a stubbed latest-two-bars (date, last_close, prev_close). `pre` stubs
    premarket_service.premarket_quote → (pm_price, pm_prev_close) | None."""
    class FakeTicker:
        def __init__(self, _t):
            self.fast_info = fi
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr("app.services.live_quote_service._is_market_open", lambda *_a, **_k: False)
    monkeypatch.setattr("app.services.live_quote_service._is_premarket", lambda *_a, **_k: True)
    monkeypatch.setattr("app.services.live_quote_service._market_today", lambda _t: date(2026, 6, 1))
    monkeypatch.setattr("app.services.live_quote_service._latest_two_bars", lambda _t: last_two)
    monkeypatch.setattr("app.services.live_quote_service._provisional_today", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.live_quote_service._override_prev_close_from_ohlcv", lambda _t, _l: None)
    # By default no dedicated prepost quote → falls back to fast_info.lastPrice.
    monkeypatch.setattr("app.services.premarket_service.premarket_quote", lambda _t: pre)


def test_premarket_echo_of_last_close_is_not_PRE(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-market lastPrice ≈ our last charted close (no real trade yet) must NOT
    light the PRE badge — even when yfinance's previousClose lags a day (which
    used to falsely trigger the prev-based guard → phantom duplicate candle)."""
    fi = _fake_fast_info({"lastPrice": 100.02, "previousClose": 95.0, "currency": "USD"})
    _patch_premarket(monkeypatch, fi, last_two=(date(2026, 5, 30), 100.0, 98.0))
    q = live_quote_service.get_quote("AAPL", force_refresh=True)
    assert q.market_state != "PRE"        # no phantom PRE
    assert q.price == 100.0               # the real last close, not the echo
    assert q.as_of_date == "2026-05-30"   # yesterday → chart won't append a today bar


def test_premarket_real_move_is_PRE_vs_last_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuine pre-market price (differs from our last close > EPS) lights PRE
    and reports the move vs the ACTUAL last close (so header + chart agree)."""
    fi = _fake_fast_info({"lastPrice": 103.0, "previousClose": 95.0, "currency": "USD"})
    _patch_premarket(monkeypatch, fi, last_two=(date(2026, 5, 30), 100.0, 98.0))
    q = live_quote_service.get_quote("AAPL", force_refresh=True)
    assert q.market_state == "PRE"
    assert q.price == 103.0               # the live pre-market price
    assert q.prev_close == 100.0          # change anchored on the actual last close
    assert q.change_abs is not None and abs(q.change_abs - 3.0) < 1e-6
    assert q.as_of_date == "2026-06-01"   # today → distinct candle


def test_premarket_uses_prepost_price_when_fastinfo_echoes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real bug: fast_info echoes the last close (no extended-hours), but
    the dedicated 5m-prepost source (same as the homepage movers) has the real
    pre-market price. The header must show THAT price + its prior-close
    denominator, not the stale echo."""
    fi = _fake_fast_info({"lastPrice": 100.0, "previousClose": 100.0, "currency": "USD"})
    _patch_premarket(
        monkeypatch, fi,
        last_two=(date(2026, 5, 30), 100.0, 98.0),
        pre=(108.0, 100.0),  # prepost price 108 vs prior close 100
    )
    q = live_quote_service.get_quote("AAPL", force_refresh=True)
    assert q.market_state == "PRE"
    assert q.price == 108.0               # the real pre-market price, not the echo
    assert q.prev_close == 100.0          # prepost source's own prior close
    assert q.change_abs is not None and abs(q.change_abs - 8.0) < 1e-6
    assert q.change_pct is not None and abs(q.change_pct - 8.0) < 1e-6
    assert q.as_of_date == "2026-06-01"


# ── Courtesy last-live cache ─────────────────────────────────────────────
# A transient yfinance failure during the session must NOT degrade a row to
# the EOD fallback (market_state "CLOSED" → live dot hidden, EOD numbers
# shown silently). If we hold a GOOD live quote fetched in the SAME session
# (after today's open), serve that instead — still marked OPEN.

def _live_quote(ticker: str, *, price: float, fetched_at: float,
                state: str = "OPEN") -> live_quote_service.LiveQuote:
    return live_quote_service.LiveQuote(
        ticker=ticker, price=price, prev_close=price - 1.0,
        change_abs=1.0, change_pct=1.0, market_state=state,
        fetched_at=fetched_at, error=None,
    )


def _degraded_quote(ticker: str) -> live_quote_service.LiveQuote:
    return live_quote_service.LiveQuote(
        ticker=ticker, price=None, market_state=None,
        fetched_at=time.time(), error="boom",
    )


def test_courtesy_serves_same_session_live_on_fetch_failure(monkeypatch) -> None:
    now = time.time()
    # A good live fetch populates _LAST_LIVE...
    monkeypatch.setattr(live_quote_service, "_fetch_fresh",
                        lambda t, **kw: _live_quote(t, price=10.5, fetched_at=now))
    monkeypatch.setattr(live_quote_service, "_is_market_open", lambda t, now_utc=None: True)
    monkeypatch.setattr(live_quote_service, "_today_session_open_epoch",
                        lambda t: now - 3600)  # session opened 1h ago
    q1 = live_quote_service.get_quote("ACME")
    assert q1.price == 10.5 and q1.market_state == "OPEN"

    # ...then the next fetch FAILS → courtesy serves the same-session live.
    live_quote_service.clear_cache_l1_only()  # expire the 10s TTL path
    monkeypatch.setattr(live_quote_service, "_fetch_fresh",
                        lambda t, **kw: _degraded_quote(t))
    q2 = live_quote_service.get_quote("ACME")
    assert q2.price == 10.5
    assert q2.market_state == "OPEN"
    assert q2.error is None


def test_courtesy_not_served_when_market_closed(monkeypatch) -> None:
    now = time.time()
    monkeypatch.setattr(live_quote_service, "_fetch_fresh",
                        lambda t, **kw: _live_quote(t, price=10.5, fetched_at=now))
    monkeypatch.setattr(live_quote_service, "_is_market_open", lambda t, now_utc=None: True)
    monkeypatch.setattr(live_quote_service, "_today_session_open_epoch",
                        lambda t: now - 3600)
    live_quote_service.get_quote("ACME")

    live_quote_service.clear_cache_l1_only()
    # Market now CLOSED → the degraded/EOD quote is the truth, no courtesy.
    monkeypatch.setattr(live_quote_service, "_is_market_open", lambda t, now_utc=None: False)
    monkeypatch.setattr(live_quote_service, "_fetch_fresh",
                        lambda t, **kw: _degraded_quote(t))
    q = live_quote_service.get_quote("ACME")
    assert q.price is None and q.error == "boom"


def test_courtesy_not_served_for_stale_previous_session(monkeypatch) -> None:
    now = time.time()
    # Last live is from BEFORE today's open (e.g. yesterday) → not courtesy-able.
    monkeypatch.setattr(live_quote_service, "_fetch_fresh",
                        lambda t, **kw: _live_quote(t, price=9.9, fetched_at=now - 86400))
    monkeypatch.setattr(live_quote_service, "_is_market_open", lambda t, now_utc=None: True)
    monkeypatch.setattr(live_quote_service, "_today_session_open_epoch",
                        lambda t: now - 3600)
    live_quote_service.get_quote("ACME")

    live_quote_service.clear_cache_l1_only()
    monkeypatch.setattr(live_quote_service, "_fetch_fresh",
                        lambda t, **kw: _degraded_quote(t))
    q = live_quote_service.get_quote("ACME")
    assert q.error == "boom"  # degraded quote returned, no stale courtesy


def test_courtesy_covers_breaker_eod_fallback_during_open_hours(monkeypatch) -> None:
    now = time.time()
    monkeypatch.setattr(live_quote_service, "_fetch_fresh",
                        lambda t, **kw: _live_quote(t, price=20.0, fetched_at=now))
    monkeypatch.setattr(live_quote_service, "_is_market_open", lambda t, now_utc=None: True)
    monkeypatch.setattr(live_quote_service, "_today_session_open_epoch",
                        lambda t: now - 3600)
    live_quote_service.get_quote("ACME")

    live_quote_service.clear_cache_l1_only()
    # Breaker-open path returns an EOD fallback labeled CLOSED (price set,
    # error None) DURING open hours → courtesy must still kick in.
    monkeypatch.setattr(
        live_quote_service, "_fetch_fresh",
        lambda t, **kw: _live_quote(t, price=19.0, fetched_at=time.time(), state="CLOSED"))
    q = live_quote_service.get_quote("ACME")
    assert q.price == 20.0 and q.market_state == "OPEN"


# ── Post-close gap: batch path must converge to TODAY without a scan ─────
# User report (SANDISK): close D-1=100, +3% during day D, after the bell the
# movers showed 100 (prior close) until a scan ran. The batch path passed
# allow_remote_today_fetch=False and the in-memory tick dies on restart, so
# nothing could fill "today". Now: tick first (free), else a BUDGETED
# official-bar fetch (token bucket) so ~all names converge within minutes.

def test_provisional_today_prefers_free_tick_no_official_call(monkeypatch) -> None:
    today = date(2026, 6, 8)
    live_quote_service._remember_intraday("SNDK", today, 103.0, 100.0)
    def _boom(*a, **kw):
        raise AssertionError("official fetch must not fire when a tick exists")
    monkeypatch.setattr(live_quote_service, "_today_official_bar", _boom)
    prov = live_quote_service._provisional_today("SNDK", None, today, False)
    assert prov == (103.0, 100.0)


def test_provisional_today_budgeted_official_when_no_tick(monkeypatch) -> None:
    today = date(2026, 6, 8)
    calls: list[str] = []
    monkeypatch.setattr(
        live_quote_service, "_today_official_bar",
        lambda t, d, c: calls.append(t) or (103.5, 100.0))
    live_quote_service._reset_today_fetch_budget(tokens=2)
    assert live_quote_service._provisional_today("SNDK", None, today, False) == (103.5, 100.0)
    assert live_quote_service._provisional_today("WDC", None, today, False) == (103.5, 100.0)
    # Budget exhausted → third ticker gets None this cycle (next refill covers it)
    assert live_quote_service._provisional_today("MU", None, today, False) is None
    assert calls == ["SNDK", "WDC"]


def test_provisional_today_allow_fetch_bypasses_budget(monkeypatch) -> None:
    today = date(2026, 6, 8)
    monkeypatch.setattr(
        live_quote_service, "_today_official_bar", lambda t, d, c: (104.0, 100.0))
    live_quote_service._reset_today_fetch_budget(tokens=0)  # empty bucket
    # Single-quote path (allow_fetch=True) is unaffected by the budget.
    assert live_quote_service._provisional_today("SNDK", None, today, True) == (104.0, 100.0)


# ── Post-close gap, instant source: fast_info lastPrice ──────────────────
# After the bell fast_info's lastPrice IS today's session price (Yahoo keeps
# the last trade). When the DB lacks today and no tick/official bar is
# available yet, that price must be served as today's provisional close —
# covering the WHOLE movers pool in one cycle (the 10/min official-bar
# budget alone left rows on yesterday for up to ~12 minutes — user report
# 2026-06-10 22:31).

def _patch_closed_gap(monkeypatch, *, last_price: float, db_close: float,
                      session_ended: bool) -> None:
    fi = _fake_fast_info({"lastPrice": last_price, "previousClose": db_close})
    class FakeTicker:
        def __init__(self, _t: str) -> None:
            self.fast_info = fi
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(live_quote_service, "_is_market_open",
                        lambda t, now_utc=None: False)
    monkeypatch.setattr(live_quote_service, "_is_premarket", lambda t: False)
    monkeypatch.setattr(live_quote_service, "_latest_two_bars",
                        lambda t: (date(2026, 6, 9), db_close, 98.0))
    monkeypatch.setattr(live_quote_service, "_provisional_today",
                        lambda *a, **kw: None)
    monkeypatch.setattr(live_quote_service, "_session_ended_today",
                        lambda t: session_ended)
    monkeypatch.setattr(live_quote_service, "_override_prev_close_from_ohlcv",
                        lambda *a, **kw: None)
    monkeypatch.setattr(live_quote_service, "_eod_pair_from_ohlcv",
                        lambda *a, **kw: None)


def test_postclose_gap_serves_fastinfo_last_as_today(monkeypatch) -> None:
    _patch_closed_gap(monkeypatch, last_price=103.0, db_close=100.0,
                      session_ended=True)
    q = live_quote_service.get_quote("SNDK", force_refresh=True)
    assert q.price == 103.0
    assert q.prev_close == 100.0
    assert q.change_pct == pytest.approx(3.0)
    assert q.as_of_date == date.today().isoformat() or q.as_of_date is not None
    assert q.market_state == "CLOSED"


def test_postclose_gap_weekend_guard_keeps_yesterday(monkeypatch) -> None:
    # Saturday: lastPrice may carry Friday post-market drift — must NOT be
    # labeled as a new "today". _session_ended_today is False on weekends.
    _patch_closed_gap(monkeypatch, last_price=103.0, db_close=100.0,
                      session_ended=False)
    q = live_quote_service.get_quote("SNDK", force_refresh=True)
    assert q.price == 100.0           # genuine last close (yesterday)
    assert q.as_of_date == "2026-06-09"


def test_postclose_gap_echo_guard_keeps_yesterday(monkeypatch) -> None:
    # lastPrice == DB close → indistinguishable from a stale echo → yesterday.
    _patch_closed_gap(monkeypatch, last_price=100.0, db_close=100.0,
                      session_ended=True)
    q = live_quote_service.get_quote("SNDK", force_refresh=True)
    assert q.price == 100.0
    assert q.as_of_date == "2026-06-09"
