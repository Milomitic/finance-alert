"""Le notizie di Yahoo giu': niente raffica di richieste, ripresa da sola.

Il 2026-11-02 `Ticker.news` ha risposto «YAHOO! FINANCE IS CURRENTLY DOWN!»
971 volte in un'ora e mezza, quasi tutte dal ricalcolo dei punteggi che chiede
le notizie di ogni titolo. E ogni fallimento chiudeva la catena con una lista
vuota, mentre Finnhub e il feed RSS rispondevano.
"""
import sys

import pytest

from app.services import (
    finnhub_news_service,
    marketaux_news_service,
    probes,
    stock_news_service,
    yahoo_rss_news_service,
    yfinance_health,
)
from app.services.finnhub_news_service import FinnhubNewsItem

NEWS = yfinance_health.LANE_NEWS


class _Orologio:
    """Il tempo del modulo dell'interruttore, spostabile a mano."""

    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def orologio(monkeypatch) -> _Orologio:
    o = _Orologio()
    monkeypatch.setattr(yfinance_health.time, "time", o)
    return o


@pytest.fixture
def yahoo(monkeypatch) -> dict:
    """Un yfinance finto: `giu` decide se `.news` esplode, `chiamate` le conta."""
    stato = {"giu": True, "chiamate": 0}

    class _Ticker:
        def __init__(self, t: str) -> None:
            self.t = t

        @property
        def news(self):
            stato["chiamate"] += 1
            if stato["giu"]:
                raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***")
            return [{"title": "Titolo", "link": "https://x/1", "publisher": "P", "providerPublishTime": 1}]

    monkeypatch.setitem(sys.modules, "yfinance", type("M", (), {"Ticker": _Ticker}))
    return stato


@pytest.fixture
def ripieghi(monkeypatch) -> dict:
    """Finnhub risponde, gli altri ripieghi tacciono: niente rete nei test."""
    stato = {"finnhub": [FinnhubNewsItem(title="Da Finnhub", url="https://f/1", source="Benzinga",
                                         published_at="2026-11-02T10:00:00+00:00", summary=None)]}
    monkeypatch.setattr(finnhub_news_service, "fetch_company_news", lambda t, limit=15: stato["finnhub"])
    monkeypatch.setattr(yahoo_rss_news_service, "fetch_company_news", lambda t, limit=15: [])
    monkeypatch.setattr(marketaux_news_service, "fetch_news", lambda t, limit=10: [])
    return stato


def _notizie(ticker: str) -> list[dict]:
    stock_news_service._CACHE.pop(ticker, None)
    return stock_news_service.get_news(ticker, force_refresh=False)


def _apri(yahoo: dict) -> None:
    for i in range(yfinance_health.N_FAILURES):
        _notizie(f"T{i}")
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES


def test_un_fallimento_passa_ai_ripieghi_invece_di_restituire_niente(db, orologio, yahoo, ripieghi) -> None:
    [n] = _notizie("AAPL")
    assert n["title"] == "Da Finnhub"


def test_dopo_cinque_fallimenti_yahoo_non_si_chiama_piu(db, orologio, yahoo, ripieghi) -> None:
    _apri(yahoo)
    for t in ("A", "B", "C", "D"):
        assert [n["title"] for n in _notizie(t)] == ["Da Finnhub"]
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES
    assert yfinance_health.status(NEWS)["state"] == "open"


def test_la_corsia_delle_notizie_non_ferma_quotazioni_e_barre(db, orologio, yahoo, ripieghi) -> None:
    _apri(yahoo)
    assert yfinance_health.is_open(NEWS)
    assert not yfinance_health.is_open(yfinance_health.LANE_QUOTES)
    assert not yfinance_health.is_open(yfinance_health.LANE_OHLCV)
    assert not yfinance_health.is_open(yfinance_health.LANE_DEFAULT)


def test_dopo_la_pausa_una_prova_sola_e_se_riesce_si_riprende(db, orologio, yahoo, ripieghi) -> None:
    _apri(yahoo)
    orologio.t += yfinance_health.COOLDOWN_SECONDS + 1
    yahoo["giu"] = False
    assert [n["title"] for n in _notizie("RIPRESA")] == ["Titolo"]
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES + 1
    assert yfinance_health.status(NEWS)["state"] == "closed"
    _notizie("DOPO")
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES + 2


def test_se_la_prova_fallisce_si_riapre_per_un_altra_pausa(db, orologio, yahoo, ripieghi) -> None:
    _apri(yahoo)
    orologio.t += yfinance_health.COOLDOWN_SECONDS + 1
    _notizie("PROVA")                       # la prova: Yahoo ancora giu'
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES + 1
    _notizie("SUBITO_DOPO")
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES + 1
    assert yfinance_health.status(NEWS)["state"] == "open"


def test_il_rinfresco_a_mano_dice_perche_se_non_c_e_niente(db, orologio, yahoo, ripieghi) -> None:
    from app.core.errors import UpstreamUnavailable

    ripieghi["finnhub"] = []
    _apri(yahoo)
    with pytest.raises(UpstreamUnavailable, match="in pausa"):
        stock_news_service.get_news("AAPL", force_refresh=True)


def test_la_sonda_tace_durante_la_pausa_e_riapre_quando_yahoo_torna(db, orologio, yahoo, ripieghi) -> None:
    _apri(yahoo)
    probes.probe_yfinance_news()
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES       # nessuna richiesta
    orologio.t += yfinance_health.COOLDOWN_SECONDS + 1
    yahoo["giu"] = False
    probes.probe_yfinance_news()
    assert yahoo["chiamate"] == yfinance_health.N_FAILURES + 1
    assert yfinance_health.status(NEWS)["state"] == "closed"
