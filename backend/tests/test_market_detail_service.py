"""Regression tests for market-detail history and cache semantics."""
from unittest.mock import patch

import pandas as pd
import pytest

from app.services import market_detail_service as svc


def teardown_function() -> None:
    svc.clear_cache()


def test_failed_fetch_is_not_cached_as_none():
    with patch.object(svc, "_fetch_fresh", return_value=None) as fetch:
        assert svc.get_detail("^GSPC", "1d") is None
        assert svc.get_detail("^GSPC", "1d") is None
        # Each call retried yfinance instead of short-circuiting on a
        # cached `None` — the old bug cached the failure for 15 minutes.
        assert fetch.call_count == 2


def test_failed_fetch_falls_back_to_stale_cached_value():
    good = svc.MarketDetailDC(symbol="^GSPC", range_key="1d")
    with patch.object(svc, "_fetch_fresh", return_value=good):
        assert svc.get_detail("^GSPC", "1d") is good

    # Force the cache to look expired, then simulate a rate-limited retry.
    key = ("^GSPC", "1d")
    with svc._CACHE_LOCK:
        ts, val = svc._CACHE[key]
        svc._CACHE[key] = (ts - svc._TTL_SECONDS - 1, val)

    with patch.object(svc, "_fetch_fresh", return_value=None):
        assert svc.get_detail("^GSPC", "1d") is good


def test_successful_fetch_is_cached_normally():
    good = svc.MarketDetailDC(symbol="^GSPC", range_key="1d")
    with patch.object(svc, "_fetch_fresh", return_value=good) as fetch:
        assert svc.get_detail("^GSPC", "1d") is good
        assert svc.get_detail("^GSPC", "1d") is good
        fetch.assert_called_once()


def _history(closes: list[float]) -> pd.DataFrame:
    """A sparse two-year history with the first close outside the last 52w."""
    index = pd.to_datetime(["2024-01-01", "2025-07-01", "2025-12-31"])
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": [1_000, 1_100, 1_200],
        },
        index=index,
    )


@pytest.mark.parametrize(
    ("range_key", "expected_history_calls"),
    [
        ("5m", 2),
        ("30m", 2),
        ("1h", 2),
        ("1d", 1),
        ("1w", 1),
        ("1m", 1),
    ],
)
def test_52w_closing_range_is_independent_from_chart_timeframe(
    range_key: str,
    expected_history_calls: int,
):
    """An all-time low outside the annual window is never labelled as 52W."""
    chart_history = _history([4.0, 100.0, 120.0])
    annual_daily_history = _history([100.0, 110.0, 120.0])

    ticker = type("Ticker", (), {})()

    def history(*, period: str, interval: str, auto_adjust: bool):
        assert auto_adjust is False
        if period == "1y" and interval == "1d":
            return annual_daily_history
        return chart_history

    ticker.history = history

    with (
        patch("yfinance.Ticker", return_value=ticker) as ticker_factory,
        patch.object(ticker, "history", wraps=ticker.history) as history_mock,
    ):
        detail = svc._fetch_fresh("^GSPC", range_key)

    assert detail is not None
    assert detail.low_window == 4.0
    assert detail.low_52w == 100.0
    assert detail.high_52w == 120.0
    assert history_mock.call_count == expected_history_calls
    assert ticker_factory.call_count == expected_history_calls


# ─── Il giornaliero del grafico: dieci anni, non dal 1927 ──────────────────

def _lungo(anni: int = 30):
    from datetime import date, timedelta

    giorni = [date(2026, 11, 13) - timedelta(days=7 * k) for k in range(anni * 52)][::-1]
    bars = [svc.OhlcvBar(d, 100 + i, 101 + i, 99 + i, 100 + i, 1) for i, d in enumerate(giorni)]
    ind = svc.IndicatorBundle(**{
        f: [svc.IndicatorPoint(d, 1.0) for d in giorni] for f in svc.IndicatorBundle.__dataclass_fields__
    })
    chiusure = [b.close for b in bars]
    return svc.MarketDetailDC(symbol="^GSPC", range_key="1d", bars=bars, indicators=ind,
                              high_window=max(chiusure), low_window=min(chiusure),
                              high_52w=max(chiusure[-52:]), low_52w=min(chiusure[-52:]))


def test_il_taglio_tiene_dieci_anni_e_ricalcola_il_periodo():
    d = _lungo()
    t = svc.taglia_agli_ultimi_anni(d)
    assert 515 <= len(t.bars) <= 525
    assert all(len(getattr(t.indicators, f)) == len(t.bars)
               for f in svc.IndicatorBundle.__dataclass_fields__)
    assert t.indicators.ema200[0].date == t.bars[0].date
    chiusure = [b.close for b in t.bars]
    assert (t.high_window, t.low_window) == (max(chiusure), min(chiusure))
    assert t.low_window > d.low_window
    assert (t.high_52w, t.low_52w) == (d.high_52w, d.low_52w)


def test_una_serie_corta_resta_com_e():
    d = _lungo(anni=3)
    assert svc.taglia_agli_ultimi_anni(d) is d


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User

    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_l_endpoint_taglia_solo_se_non_si_chiede_la_storia_completa(client):
    with patch.object(svc, "get_detail", return_value=_lungo()), \
         patch("app.services.live_quote_service.get_quote", return_value=None):
        recente = client.get("/api/markets/%5EGSPC/detail?range=1d").json()
        completa = client.get("/api/markets/%5EGSPC/detail?range=1d&storia=completa").json()
        settimanale = client.get("/api/markets/%5EGSPC/detail?range=1w").json()
    assert len(completa["bars"]) == 30 * 52
    assert len(recente["bars"]) < 530
    assert len(recente["indicators"]["rsi14"]) == len(recente["bars"])
    # Il taglio vale per le barre giornaliere; la chiave la decide il servizio.
    assert len(settimanale["bars"]) < 530


# ─── FA-180: a cash chiuso la pagina mostra il future, come la home ────────

def _quotazioni(stato_cash: str):
    from app.services.live_quote_service import LiveQuote

    tabella = {
        "^IXIC": LiveQuote(ticker="^IXIC", price=23585.8, prev_close=23700.0, change_pct=-0.48,
                           market_state=stato_cash),
        "NQ=F": LiveQuote(ticker="NQ=F", price=26658.25, prev_close=25962.25, change_pct=2.68,
                          market_state="CLOSED"),
    }
    return lambda t, **k: tabella[t]


def test_a_cash_chiuso_la_pagina_dell_indice_mostra_il_future(client):
    with patch.object(svc, "get_detail", return_value=_lungo()), \
         patch("app.services.live_quote_service.get_quote", side_effect=_quotazioni("CLOSED")):
        d = client.get("/api/markets/%5EIXIC/detail?range=1d").json()
    assert d["using_futures"] is True
    assert d["quote_symbol"] == "NQ=F"
    assert d["quote"]["change_pct"] == 2.68


def test_a_cash_aperto_resta_il_cash(client):
    with patch.object(svc, "get_detail", return_value=_lungo()), \
         patch("app.services.live_quote_service.get_quote", side_effect=_quotazioni("OPEN")):
        d = client.get("/api/markets/%5EIXIC/detail?range=1d").json()
    assert d["using_futures"] is False
    assert d["quote_symbol"] == "^IXIC"
    assert d["quote"]["change_pct"] == -0.48


def test_la_home_e_la_pagina_scelgono_con_la_stessa_regola():
    """Un proprietario solo: il paniere della home passa dalla stessa funzione."""
    import inspect

    from app.api import market

    assert "quotazione_da_mostrare(" in inspect.getsource(market._paniere)
    # FA-190: home e mercati estesi passano entrambi da `_paniere`.
    assert "_paniere(LIVE_ASSET_DEFINITIONS)" in inspect.getsource(market.calcola_paniere)
    assert "_paniere(MERCATI_ESTESI)" in inspect.getsource(market.calcola_estesi)
