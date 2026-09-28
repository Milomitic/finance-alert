"""multi-tf-kpis: the per-timeframe fetches are parallelized for the yfinance
(intraday) timeframes while DB-backed ones stay on the calling thread.

Guards: (1) output order still matches VALID_TIMEFRAMES; (2) the Session is
never handed to a worker thread (yfinance timeframes are fetched with no db);
(3) every timeframe is computed exactly once."""
from __future__ import annotations

from types import SimpleNamespace

from app.api import multi_tf
from app.services.timeframe_service import _INTRADAY, VALID_TIMEFRAMES


def _fake_kpis(tf: str) -> SimpleNamespace:
    return SimpleNamespace(
        timeframe=tf, bars=1, last_close=1.0, rsi=None, rsi_tone="n",
        ema20=None, ema50=None, ema200=None,
        ema20_above=None, ema50_above=None, ema200_above=None,
        bb_upper=None, bb_middle=None, bb_lower=None, bb_position=None,
        macd_line=None, macd_signal=None, macd_hist=None, macd_tone="n",
        composite_score=0, composite_label="x",
    )


def test_stock_path_parallelizes_only_yfinance_timeframes(monkeypatch):
    seen: list[tuple[str, bool]] = []  # (timeframe, db_was_passed)

    def fake_fetch(*, ticker, timeframe, db=None, stock=None):
        seen.append((timeframe, db is not None))
        return [timeframe]  # stand-in bars

    monkeypatch.setattr(multi_tf, "fetch_bars", fake_fetch)
    monkeypatch.setattr(multi_tf, "compute_timeframe_kpis", lambda bars, tf: _fake_kpis(tf))

    sentinel_db = object()
    items = multi_tf._compute_multi_tf("AAPL", db=sentinel_db, stock=object())

    # Order preserved regardless of parallel completion order.
    assert [it.timeframe for it in items] == list(VALID_TIMEFRAMES)
    # Every timeframe fetched exactly once.
    assert sorted(tf for tf, _ in seen) == sorted(VALID_TIMEFRAMES)
    # Intraday (yfinance) timeframes fetched WITHOUT db; daily WITH db.
    by_tf = dict(seen)
    for tf in VALID_TIMEFRAMES:
        assert by_tf[tf] is (tf not in _INTRADAY)


def test_market_path_has_no_db(monkeypatch):
    seen: list[tuple[str, bool]] = []

    def fake_fetch(*, ticker, timeframe, db=None, stock=None):
        seen.append((timeframe, db is not None))
        return [timeframe]

    monkeypatch.setattr(multi_tf, "fetch_bars", fake_fetch)
    monkeypatch.setattr(multi_tf, "compute_timeframe_kpis", lambda bars, tf: _fake_kpis(tf))

    items = multi_tf._compute_multi_tf("^GSPC")  # no db
    assert [it.timeframe for it in items] == list(VALID_TIMEFRAMES)
    # A market symbol never has a db → no worker ever receives one.
    assert all(db_passed is False for _, db_passed in seen)


# ── FA-110: solo i timeframe chiesti ──────────────────────────────────────


def _registra(monkeypatch) -> list[str]:
    visti: list[str] = []

    def fake_fetch(*, ticker, timeframe, db=None, stock=None):
        visti.append(timeframe)
        return [timeframe]

    monkeypatch.setattr(multi_tf, "fetch_bars", fake_fetch)
    monkeypatch.setattr(multi_tf, "compute_timeframe_kpis", lambda bars, tf: _fake_kpis(tf))
    return visti


def test_i_giornalieri_non_toccano_yahoo(monkeypatch):
    """Il gruppo che la pagina titolo chiede per primo: tutto dal database,
    nessun timeframe intraday scaricato."""
    visti = _registra(monkeypatch)
    items = multi_tf._compute_multi_tf("AAPL", db=object(), stock=object(), timeframes=["1d", "1w", "1m"])
    assert [it.timeframe for it in items] == ["1d", "1w", "1m"]
    assert not set(visti) & _INTRADAY


def test_5m_e_30m_non_si_scaricano_se_nessuno_li_chiede(monkeypatch):
    """Il frontend non li mostra: prima si scaricavano a ogni apertura."""
    visti = _registra(monkeypatch)
    multi_tf._compute_multi_tf("AAPL", db=object(), stock=object(), timeframes=["1h"])
    assert visti == ["1h"]


def test_l_ordine_resta_quello_canonico(monkeypatch):
    _registra(monkeypatch)
    items = multi_tf._compute_multi_tf("^GSPC", timeframes=["1m", "1h", "1d"])
    assert [it.timeframe for it in items] == ["1h", "1d", "1m"]


def test_il_parametro(monkeypatch):
    import pytest
    from fastapi import HTTPException

    assert multi_tf._timeframes_richiesti(None) is None
    assert multi_tf._timeframes_richiesti("1h, 1d") == ["1h", "1d"]
    for sbagliato in ["", "1h,all", "4h"]:
        with pytest.raises(HTTPException) as e:
            multi_tf._timeframes_richiesti(sbagliato)
        assert e.value.status_code == 422


# ── gli endpoint, fino alla risposta ──────────────────────────────────────


def test_gli_endpoint_rispettano_timeframes(monkeypatch, db):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import Stock, User

    visti = _registra(monkeypatch)
    user = User(username="admin", password_hash="x")
    db.add_all([user, Stock(ticker="AAPL", exchange="NASDAQ", name="Apple", country="US")])
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        c = TestClient(app)
        r = c.get("/api/stocks/AAPL/multi-tf-kpis?timeframes=1d,1w")
        assert r.status_code == 200
        assert [i["timeframe"] for i in r.json()["items"]] == ["1d", "1w"]
        assert c.get("/api/markets/^GSPC/multi-tf-kpis?timeframes=1h").json()["items"][0]["timeframe"] == "1h"
        assert c.get("/api/stocks/AAPL/multi-tf-kpis?timeframes=all").status_code == 422
        # Senza parametro: tutti, come prima (compatibilita').
        assert len(c.get("/api/stocks/AAPL/multi-tf-kpis").json()["items"]) == len(VALID_TIMEFRAMES)
    finally:
        app.dependency_overrides.clear()
    assert visti[:3] == ["1d", "1w", "1h"]
