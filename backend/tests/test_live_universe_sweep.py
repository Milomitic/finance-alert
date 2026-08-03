"""Rotating universe live-movers sweep: stage change% open-only, rank fresh."""
from types import SimpleNamespace

from app.models import Stock
from app.services import live_universe_sweep_service as sweep


def setup_function():
    sweep.clear()


def _q(change_pct, price=10.0, error=None):
    return SimpleNamespace(change_pct=change_pct, price=price, error=error)


def test_record_and_rank():
    sweep.record_quotes({
        "AAA": _q(8.0), "BBB": _q(-5.0), "CCC": _q(2.0), "DDD": _q(-9.0),
        "ERR": _q(20.0, error="boom"), "NOP": _q(None),
    })
    m = sweep.get_live_movers(top_n=2)
    assert [g["ticker"] for g in m["gainers"]] == ["AAA", "CCC"]
    assert [l["ticker"] for l in m["losers"]] == ["DDD", "BBB"]
    assert m["swept"] == 4  # ERR + NOP skipped


def test_stale_entries_drop_out(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(sweep, "_now", lambda: t[0])
    sweep.record_quotes({"AAA": _q(5.0)})
    t[0] = 1000.0 + sweep.settings.live_movers_stale_seconds + 1  # past TTL
    assert sweep.get_live_movers()["swept"] == 0


def test_refresh_chunk_fetches_only_open_market(db, monkeypatch):
    for tk in ("US1", "US2", "HK1.HK"):
        db.add(Stock(ticker=tk, exchange="X", name=tk, country="US"))
    db.commit()
    fetched = {}
    def fake_batch(tickers):
        fetched["arg"] = list(tickers)
        return {t: _q(3.0) for t in tickers}
    # HK closed, US open
    sweep.refresh_chunk(db, batch_fn=fake_batch, is_open=lambda t: not t.endswith(".HK"))
    assert "HK1.HK" not in fetched["arg"]
    assert set(fetched["arg"]) == {"US1", "US2"}
    assert sweep.get_live_movers()["swept"] == 2


def test_refresh_chunk_no_open_tickers_no_fetch(db):
    db.add(Stock(ticker="HK1.HK", exchange="X", name="x", country="HK"))
    db.commit()
    called = {"n": 0}
    def fake_batch(tickers):
        called["n"] += 1
        return {}
    # Invariant refined 2026-08-03: "all closed" alone is no longer the whole
    # condition. A closed market we hold NOTHING for is still fetched once, or
    # its dashboard row can never fill (that shipped, and showed as FTSE MIB
    # and CSI 300 sitting blank). Nothing open AND nothing missing is what
    # genuinely warrants no upstream call.
    n = sweep.refresh_chunk(
        db, batch_fn=fake_batch, is_open=lambda t: False, has_value=lambda t: True,
    )
    assert n == 0 and called["n"] == 0  # never hit yfinance with nothing to gain


def test_sweep_job_runs_intraday_price_eval_even_if_sweep_fails(monkeypatch):
    """The scheduler tick piggybacks evaluate_intraday; a sweep crash must
    not prevent the price-alert evaluation (and vice versa: neither may
    propagate out of the job)."""
    from app.scheduler.jobs import live_movers_sweep as job

    monkeypatch.setattr(
        job.live_universe_sweep_service, "refresh_chunk",
        lambda db: (_ for _ in ()).throw(RuntimeError("sweep boom")),
    )
    called = {"n": 0}
    monkeypatch.setattr(
        job.price_alert_service, "evaluate_intraday",
        lambda db: called.__setitem__("n", called["n"] + 1),
    )
    job.run_live_universe_sweep()  # must not raise
    assert called["n"] == 1


def test_the_dashboard_indices_are_warmed_even_though_they_are_not_in_the_catalog(db):
    """The gap that made the dashboard's first panel render "—" for all 18
    rows at once.

    Indices, commodities and crypto are deliberately absent from the `Stock`
    catalog, so the rotation never reaches them, and they have no rows in
    `ohlcv_daily` either. Every rung of the live-quote fallback ladder is
    therefore empty for them — no warm cache, no last-good, no L2 snapshot, no
    EOD close — and a live fetch that misses the interactive deadline leaves
    literally nothing to show. The sweep is the only place that can put a
    floor under them."""
    db.add(Stock(ticker="US1", exchange="X", name="x", country="US"))
    db.commit()
    seen: list[list[str]] = []

    def fake_batch(tickers):
        seen.append(list(tickers))
        return {}

    sweep.refresh_chunk(db, batch_fn=fake_batch, is_open=lambda t: True)

    warmed = {s for call in seen for s in call}
    assert "^GSPC" in warmed, "the S&P index must be warmed by the sweep"
    assert "BTC-USD" in warmed
    assert "ES=F" in warmed, "the futures pair is what the panel swaps to after hours"


def test_warmed_indices_are_not_staged_as_movers(db):
    """An index is not a mover. Warming must not leak into that list."""
    db.add(Stock(ticker="US1", exchange="X", name="x", country="US"))
    db.commit()
    sweep.refresh_chunk(
        db,
        batch_fn=lambda tickers: {
            t: type("Q", (), {"price": 1.0, "change_pct": 1.0, "error": None})()
            for t in tickers
        },
        is_open=lambda t: True,
    )
    movers = sweep.get_live_movers()
    rows = [r for side in ("gainers", "losers") for r in movers.get(side, [])]
    assert not [r for r in rows if str(r.get("ticker", "")).startswith("^")]


def test_a_closed_market_is_warmed_when_we_hold_nothing_for_it(db):
    """The gap the first version of the warm shipped with.

    Gating purely on is_open assumed the symbol had been warmed earlier in the
    session. From cold that assumption excludes itself: a pod starting after
    Milan and Shanghai close never warms them, L2 holds nothing, and those two
    rows stay blank until the next open. The dashboard showed exactly that —
    every open market populated, only FTSE MIB and CSI 300 empty."""
    db.add(Stock(ticker="US1", exchange="X", name="x", country="US"))
    db.commit()
    seen: list[str] = []
    sweep.refresh_chunk(
        db,
        batch_fn=lambda tickers: (seen.extend(tickers), {})[1],
        is_open=lambda t: False,           # everything shut
        has_value=lambda t: False,         # and nothing held
    )
    assert "FTSEMIB.MI" in seen, "a closed market with no data must still be fetched once"
    assert "000300.SS" in seen


def test_a_closed_market_we_already_hold_is_left_alone(db):
    """The other half: once a price is held, re-fetching a shut market buys
    nothing and spends the Yahoo budget the rate-limiting incident taught us
    to respect."""
    db.add(Stock(ticker="US1", exchange="X", name="x", country="US"))
    db.commit()
    seen: list[str] = []
    sweep.refresh_chunk(
        db,
        batch_fn=lambda tickers: (seen.extend(tickers), {})[1],
        is_open=lambda t: False,
        has_value=lambda t: True,          # already held
    )
    assert seen == [], "nothing is open and nothing is missing — no reason to fetch"
