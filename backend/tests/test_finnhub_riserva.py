"""Le quotazioni di riserva da Finnhub col breaker di Yahoo aperto (FA-158)."""
import pytest

from app.core.config import settings
from app.services import finnhub_quote_service as fq
from app.services import live_quote_service as lq
from app.services import yfinance_health


class Risposta:
    def __init__(self, codice, corpo):
        self.status_code, self._corpo = codice, corpo

    def json(self):
        return self._corpo


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    monkeypatch.setattr(settings, "finnhub_api_key", "k")
    fq.azzera_limite()
    with lq._CACHE_LOCK:
        lq._CACHE.clear()
    yield
    fq.azzera_limite()
    with lq._CACHE_LOCK:
        lq._CACHE.clear()


def test_solo_titoli_usa_e_solo_con_la_chiave(monkeypatch):
    assert fq.disponibile("AAPL") and not fq.disponibile("UCG.MI") and not fq.disponibile("^GSPC")
    monkeypatch.setattr(settings, "finnhub_api_key", "")
    assert not fq.disponibile("AAPL")


def test_la_risposta_e_il_simbolo_sconosciuto(monkeypatch):
    corpo = {"c": 110.0, "pc": 100.0, "o": 101.0, "h": 112.0, "l": 99.0, "t": 1763150400}
    monkeypatch.setattr(fq.requests, "get", lambda *a, **k: Risposta(200, corpo))
    d = fq.quota("AAPL")
    assert d["price"] == 110.0 and d["change_pct"] == pytest.approx(10.0)
    monkeypatch.setattr(fq.requests, "get", lambda *a, **k: Risposta(200, {"c": 0, "pc": 0}))
    assert fq.quota("ZZZZ") is None
    monkeypatch.setattr(fq.requests, "get", lambda *a, **k: Risposta(429, {}))
    assert fq.quota("AAPL") is None

    def guasto(*a, **k):
        raise fq.requests.ConnectionError("giu")
    monkeypatch.setattr(fq.requests, "get", guasto)
    assert fq.quota("AAPL") is None


def test_il_tetto_al_minuto(monkeypatch):
    chiamate = []
    monkeypatch.setattr(fq.requests, "get", lambda *a, **k: chiamate.append(1) or Risposta(200, {"c": 1.0}))
    monkeypatch.setattr(fq, "PER_MINUTO", 3)
    risposte = [fq.quota("AAPL", ora=lambda: 1000.0) for _ in range(5)]
    assert sum(r is not None for r in risposte) == 3 and len(chiamate) == 3
    assert fq.quota("AAPL", ora=lambda: 1061.0) is not None      # un minuto dopo si riparte


def test_col_breaker_aperto_il_prezzo_viene_da_finnhub_e_lo_dice(monkeypatch):
    monkeypatch.setattr(yfinance_health, "is_open", lambda lane=None: True)
    monkeypatch.setattr(fq.requests, "get",
                        lambda *a, **k: Risposta(200, {"c": 210.0, "pc": 200.0, "t": 1763150400}))
    q = lq._fetch_fresh("AAPL")
    assert (q.price, q.source, q.currency, q.as_of_date) == (210.0, "finnhub", "USD", "2025-11-14")
    # Entro il minuto non si richiede: la cache basta.
    monkeypatch.setattr(fq.requests, "get", lambda *a, **k: pytest.fail("richiesta inattesa"))
    assert lq._riserva("AAPL").price == 210.0
    # Un titolo non USA torna al ripiego di prima (l'ultima chiusura salvata).
    monkeypatch.setattr(lq, "_eod_fallback_quote", lambda t: lq.LiveQuote(ticker=t, price=1.0))
    assert lq._fetch_fresh("UCG.MI").source is None


def test_nel_lotto_la_riserva_prima_del_ripiego(monkeypatch):
    monkeypatch.setattr(yfinance_health, "is_open", lambda lane=None: True)
    monkeypatch.setattr(lq, "_riserva", lambda t: lq.LiveQuote(ticker=t, price=5.0, source="finnhub")
                        if t == "AAPL" else None)
    monkeypatch.setattr(lq, "_warm_or_eod", lambda t: lq.LiveQuote(ticker=t, price=1.0))
    out = lq.get_quotes_batch(["AAPL", "UCG.MI"])
    assert out["AAPL"].source == "finnhub" and out["UCG.MI"].price == 1.0
