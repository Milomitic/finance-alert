"""Wrapper Marketaux: parsing del JSON, gestione errori, no-key short-circuit."""
from unittest.mock import patch

import pytest

from app.core.errors import UpstreamUnavailable
from app.services.marketaux_news_service import _clear_caches_for_tests, fetch_news


@pytest.fixture(autouse=True)
def _reset_marketaux_state():
    """The service has a 12h per-ticker response cache + a circuit
    breaker. Without resetting between tests, the second test that
    fetches AAPL would hit the cache populated by the first and skip
    the HTTP mock entirely — silently masking the test's expectations.
    """
    _clear_caches_for_tests()
    yield
    _clear_caches_for_tests()


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


def test_scrubber_redacts_api_token_in_text():
    """Marketaux error bodies sometimes echo the api_token in JSON. The
    scrubber must replace it with [REDACTED] before we log the body, so
    secrets don't leak to production logs."""
    from app.services.marketaux_news_service import _scrub_token

    # query-string style
    assert "[REDACTED]" in _scrub_token("error: api_token=sk-abc123 invalid")
    assert "sk-abc123" not in _scrub_token("error: api_token=sk-abc123 invalid")

    # JSON style (single quotes)
    assert "[REDACTED]" in _scrub_token('{"api_token":"sk-abc123"}')
    assert "sk-abc123" not in _scrub_token('{"api_token":"sk-abc123"}')

    # JSON style (double quotes inside a Python string)
    assert "[REDACTED]" in _scrub_token('{"api_token": "sk-abc123"}')
    assert "sk-abc123" not in _scrub_token('{"api_token": "sk-abc123"}')

    # Negative: a string that doesn't contain the token is unchanged
    assert _scrub_token("plain error message") == "plain error message"


def test_returns_empty_list_when_marketaux_data_is_empty(monkeypatch):
    """A successful 200 response with empty `data` array must return []
    cleanly — same shape as the no-key path. This is distinct from an HTTP
    error and from a missing key, and we should be able to tell them
    apart in tests (and indirectly in metrics, since this path doesn't
    log a warning)."""
    monkeypatch.setattr(
        "app.services.marketaux_news_service.settings.marketaux_api_key", "fake-key"
    )
    with patch(
        "app.services.marketaux_news_service.requests.get"
    ) as mget:
        mget.return_value.status_code = 200
        mget.return_value.json.return_value = {"data": []}
        items = fetch_news("AAPL")
    assert items == []
