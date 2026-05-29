"""Tests for stock_news_service."""
from datetime import UTC, datetime, timedelta

from app.services import stock_news_service


def test_normalize_handles_complete_item():
    raw = {
        "title": "Apple beats Q3",
        "link": "https://example.com/news/123",
        "publisher": "Reuters",
        "providerPublishTime": 1714694400,
    }
    n = stock_news_service._normalize_yf_item(raw)
    assert n is not None
    assert n["title"] == "Apple beats Q3"
    assert n["publisher"] == "Reuters"
    assert n["published_at"] is not None


def test_normalize_skips_missing_title_or_link():
    assert stock_news_service._normalize_yf_item({"link": "x"}) is None
    assert stock_news_service._normalize_yf_item({"title": "x"}) is None


def test_normalize_handles_new_nested_shape():
    """yfinance ≥ ~0.2.40 returns {id, content: {title, pubDate, canonicalUrl, ...}}.
    Regression: prior to the fix every new-shape item was dropped (None) so
    the News card showed empty for every ticker."""
    raw = {
        "id": "abc-123",
        "content": {
            "id": "abc-123",
            "contentType": "STORY",
            "title": "Apple Q3 beats expectations",
            "summary": "...",
            "pubDate": "2026-05-04T10:00:00Z",
            "displayTime": "2026-05-04T10:00:15Z",
            "provider": {
                "displayName": "Yahoo Finance",
                "sourceId": "yahoofinance.com",
            },
            "canonicalUrl": {
                "url": "https://finance.yahoo.com/news/aapl-q3.html",
            },
            "clickThroughUrl": {
                "url": "https://yahoo.com/wrapper/aapl-q3.html",
            },
        },
    }
    n = stock_news_service._normalize_yf_item(raw)
    assert n is not None
    assert n["title"] == "Apple Q3 beats expectations"
    assert n["publisher"] == "Yahoo Finance"
    # canonicalUrl is preferred over clickThroughUrl
    assert n["link"] == "https://finance.yahoo.com/news/aapl-q3.html"
    # pubDate string is passed through as-is (already ISO8601)
    assert n["published_at"] == "2026-05-04T10:00:00Z"


def test_normalize_new_shape_falls_back_to_clickthrough_when_no_canonical():
    raw = {
        "id": "x",
        "content": {
            "title": "T",
            "clickThroughUrl": {"url": "https://yahoo.com/x"},
            "pubDate": "2026-05-04T10:00:00Z",
        },
    }
    n = stock_news_service._normalize_yf_item(raw)
    assert n is not None
    assert n["link"] == "https://yahoo.com/x"
    assert n["publisher"] == "Unknown"  # no provider in this fixture


def test_get_news_cache_hit(monkeypatch):
    stock_news_service.clear_cache()
    calls: list[str] = []

    class FakeTicker:
        def __init__(self, t): self._t = t
        @property
        def news(self):
            calls.append(self._t)
            return [{"title": "T", "link": "L", "publisher": "P", "providerPublishTime": 1}]

    fake_module = type("M", (), {"Ticker": FakeTicker})
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    a = stock_news_service.get_news("AAPL")
    b = stock_news_service.get_news("AAPL")
    assert len(a) == 1 and len(b) == 1
    assert calls == ["AAPL"]   # cached on second call


def test_get_news_fallback_on_yfinance_error(monkeypatch):
    stock_news_service.clear_cache()

    class BoomTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            raise RuntimeError("network down")

    fake_module = type("M", (), {"Ticker": BoomTicker})
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    items = stock_news_service.get_news("AAPL")
    assert items == []


def test_get_news_force_refresh_raises_on_yfinance_error(monkeypatch):
    """A forced refresh surfaces the upstream failure (so the card can show the
    error text) instead of silently returning []."""
    import pytest

    from app.core.errors import UpstreamUnavailable

    stock_news_service.clear_cache()

    class BoomTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            raise RuntimeError("network down")

    fake_module = type("M", (), {"Ticker": BoomTicker})
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    with pytest.raises(UpstreamUnavailable):
        stock_news_service.get_news("AAPL", force_refresh=True)


def test_falls_back_to_marketaux_when_yfinance_empty(monkeypatch):
    """Se yfinance ritorna 0 headline e Finnhub torna vuoto, il
    service prova Marketaux come ultima fallback.

    Aggiornato dopo l'aggiunta di Finnhub come fallback prioritario:
    ora la pipeline è yfinance → finnhub → marketaux. Per testare
    che marketaux sia raggiunto serve mockare anche finnhub a vuoto."""
    from app.services import finnhub_news_service, marketaux_news_service

    stock_news_service.clear_cache()

    def fake_finnhub_empty(ticker: str, *, days_back: int = 14, limit: int = 20):
        return []

    monkeypatch.setattr(
        finnhub_news_service, "fetch_company_news", fake_finnhub_empty
    )

    def fake_marketaux(ticker: str, limit: int = 10):
        return [
            marketaux_news_service.NewsItem(
                title="From marketaux fallback",
                url="https://x",
                published_at="2026-05-15T00:00:00Z",
                source="Reuters",
            )
        ]

    monkeypatch.setattr(marketaux_news_service, "fetch_news", fake_marketaux)

    # yfinance returns empty news list
    class EmptyTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            return []

    fake_module = type("M", (), {"Ticker": EmptyTicker})
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    result = stock_news_service.get_news("AAPL")
    assert len(result) == 1
    assert "marketaux fallback" in result[0]["title"].lower()


def test_falls_back_to_finnhub_when_yfinance_empty(monkeypatch):
    """Se yfinance ritorna 0 headline, il service prova Finnhub PRIMA
    di Marketaux (priorità per la sua quota più generosa, 60/min vs
    100/giorno). Marketaux non deve essere consultato in questo caso."""
    from app.services import finnhub_news_service, marketaux_news_service

    stock_news_service.clear_cache()

    def fake_finnhub(ticker: str, *, days_back: int = 14, limit: int = 20):
        return [
            finnhub_news_service.FinnhubNewsItem(
                title="From finnhub fallback",
                url="https://finnhub.example/apple-target",
                published_at="2026-05-15T12:00:00+00:00",
                source="Benzinga",
                summary="Wedbush raises Apple target.",
            )
        ]

    monkeypatch.setattr(
        finnhub_news_service, "fetch_company_news", fake_finnhub
    )

    # Marketaux must NOT be called when Finnhub already returned data.
    marketaux_calls = []

    def boom_marketaux(ticker, limit=10):
        marketaux_calls.append(ticker)
        return []

    monkeypatch.setattr(marketaux_news_service, "fetch_news", boom_marketaux)

    class EmptyTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            return []

    fake_module = type("M", (), {"Ticker": EmptyTicker})
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    result = stock_news_service.get_news("AAPL")
    assert len(result) == 1
    assert "finnhub fallback" in result[0]["title"].lower()
    assert marketaux_calls == [], (
        "Marketaux should not be consulted when Finnhub already produced "
        "headlines — the latter has 60/min quota vs the former's 100/day."
    )


def test_news_hydrate_l1_returns_tuple(db):
    """hydrate_l1_from_db deve tornare (loaded, skipped) anche per news."""
    result = stock_news_service.hydrate_l1_from_db()
    assert isinstance(result, tuple)
    assert result == (0, 0)
