"""Finnhub `/company-news` solo sui listini USA: altrove il piano gratuito
risponde 403, e chiederlo consumava budget e sporcava la salute della fonte."""
import pytest

from app.services import data_source_metrics
from app.services import finnhub_news_service as svc


@pytest.fixture
def rete(monkeypatch):
    chiamate: list[str] = []
    fallimenti: list[str] = []

    class Risposta:
        status_code = 403

        def json(self):
            return []

    def get(url, params=None, **kw):
        chiamate.append(params["symbol"])
        return Risposta()

    monkeypatch.setattr(svc, "is_enabled", lambda: True)
    monkeypatch.setattr(svc, "_is_blocked", lambda scope=None: (False, ""))
    monkeypatch.setattr(svc, "_rate_limited", lambda ceiling: False)
    monkeypatch.setattr(svc.requests, "get", get)
    monkeypatch.setattr(data_source_metrics, "record_failure", lambda *a, **k: fallimenti.append(a[1]))
    svc._NEWS_CACHE.clear()
    return chiamate, fallimenti


@pytest.mark.parametrize("ticker", ["0005.HK", "7203.T", "IAG.L", "RWE.DE", "UNI.MI", "005930.KS"])
def test_un_titolo_estero_non_chiama_finnhub(rete, ticker) -> None:
    chiamate, fallimenti = rete
    assert svc.fetch_company_news(ticker) == []
    assert (chiamate, fallimenti) == ([], [])


@pytest.mark.parametrize("ticker", ["AAPL", "BRK-B", "BF-B"])
def test_un_titolo_usa_la_chiama(rete, ticker) -> None:
    """Controllo negativo: la guardia non spegne la fonte per tutti."""
    chiamate, fallimenti = rete
    svc.fetch_company_news(ticker)
    assert chiamate == [ticker]
    # Il 403 finto di questa fixture, su un titolo USA, resta un fallimento vero.
    assert fallimenti == ["news"]
