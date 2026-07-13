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
    n = sweep.refresh_chunk(db, batch_fn=fake_batch, is_open=lambda t: False)
    assert n == 0 and called["n"] == 0  # never hit yfinance when all closed


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
