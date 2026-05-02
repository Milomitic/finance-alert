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
