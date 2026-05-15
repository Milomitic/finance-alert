"""Wrapper Marketaux: parsing del JSON, gestione errori, no-key short-circuit."""
from unittest.mock import patch

import pytest

from app.core.errors import UpstreamUnavailable
from app.services.marketaux_news_service import fetch_news


def test_returns_empty_when_no_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.marketaux_news_service.settings.marketaux_api_key", ""
    )
    assert fetch_news("AAPL") == []


def test_parses_marketaux_response(monkeypatch):
    monkeypatch.setattr(
        "app.services.marketaux_news_service.settings.marketaux_api_key", "fake-key"
    )
    payload = {
        "data": [
            {
                "uuid": "abc",
                "title": "Apple beats Q4 estimates",
                "url": "https://news.example/apple-q4",
                "published_at": "2026-05-15T12:00:00Z",
                "source": "Reuters",
            }
        ]
    }
    with patch(
        "app.services.marketaux_news_service.requests.get"
    ) as mget:
        mget.return_value.status_code = 200
        mget.return_value.json.return_value = payload
        items = fetch_news("AAPL")
    assert len(items) == 1
    assert items[0].title.startswith("Apple beats")
    assert items[0].url == "https://news.example/apple-q4"


def test_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.marketaux_news_service.settings.marketaux_api_key", "fake-key"
    )
    with patch(
        "app.services.marketaux_news_service.requests.get"
    ) as mget:
        mget.return_value.status_code = 503
        mget.return_value.text = "down"
        with pytest.raises(UpstreamUnavailable):
            fetch_news("AAPL")
