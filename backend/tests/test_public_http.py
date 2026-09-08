"""SSRF boundaries: blocked addresses, redirect revalidation and pinned TLS."""
import io
import socket
from unittest.mock import MagicMock

import pytest

from app.core import public_http as public
from app.services import news_body_fetcher as articles


def _dns(monkeypatch, addresses=("93.184.216.34",)):
    calls = []

    def resolve(host, port, **_):
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in addresses]

    monkeypatch.setattr(public.socket, "getaddrinfo", resolve)
    return calls


def _pool(monkeypatch, *, status=200, headers=None, body=b"<p>Public article</p>"):
    response = MagicMock()
    response.status = status
    response.headers = headers or {"Content-Type": "text/html"}
    reader = io.BytesIO(body)
    response.read1.side_effect = lambda n, **_: reader.read(n)
    pool = MagicMock()
    pool.__enter__.return_value = pool
    pool.urlopen.return_value = response
    factory = MagicMock(return_value=pool)
    monkeypatch.setattr(public.urllib3, "HTTPSConnectionPool", factory)
    monkeypatch.setattr(public.urllib3, "HTTPConnectionPool", factory)
    return factory, pool, response


def _fetch(url="https://example.org/article", limit=100):
    return public.fetch_public_text(url, max_bytes=limit, timeout=5, user_agent="test")


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
    "0.0.0.0", "::1", "fc00::1", "fe80::1", "224.0.0.1", "::ffff:127.0.0.1",
    "64:ff9b::a9fe:a9fe", "2002:7f00:1::",
])
def test_private_or_special_resolution_never_opens_connection(monkeypatch, address):
    _dns(monkeypatch, (address,))
    factory, _, _ = _pool(monkeypatch)
    with pytest.raises(ValueError):
        _fetch()
    factory.assert_not_called()


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.org/a", "https://user:secret@example.org/a",
    "https://example.org:8443/a", "https://example.org/\r\nHost: localhost",
    "https://example.org:0/a",
    "https://[fe80::1%25eth0]/a", "https://example.org/" + "a" * 4096,
])
def test_invalid_url_never_reaches_dns(monkeypatch, url):
    calls = _dns(monkeypatch)
    with pytest.raises(ValueError):
        _fetch(url)
    assert not calls


def test_mixed_public_and_private_dns_is_rejected(monkeypatch):
    _dns(monkeypatch, ("93.184.216.34", "10.0.0.1"))
    factory, _, _ = _pool(monkeypatch)
    with pytest.raises(ValueError):
        _fetch()
    factory.assert_not_called()


def test_connects_to_validated_ip_with_original_tls_identity(monkeypatch):
    calls = _dns(monkeypatch)
    factory, pool, response = _pool(monkeypatch)
    assert "Public article" in _fetch()
    args = factory.call_args.kwargs
    assert args["host"] == "93.184.216.34"
    assert args["server_hostname"] == args["assert_hostname"] == "example.org"
    assert args["cert_reqs"] == public.ssl.CERT_REQUIRED
    assert calls == ["example.org"]
    assert pool.urlopen.call_args.kwargs["headers"]["Host"] == "example.org"
    assert pool.urlopen.call_args.kwargs["redirect"] is False
    response.close.assert_called_once()


def test_redirect_to_metadata_is_rejected_before_second_connection(monkeypatch):
    def resolve(host, port, **_):
        ip = "169.254.169.254" if host == "metadata.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(public.socket, "getaddrinfo", resolve)
    factory, _, response = _pool(
        monkeypatch, status=302, headers={"Location": "https://metadata.example/keys"},
    )
    with pytest.raises(ValueError, match="Non-public"):
        _fetch()
    assert factory.call_count == 1
    response.close.assert_called_once()


def test_redirect_loop_is_bounded_and_connections_close(monkeypatch):
    _dns(monkeypatch)
    factory, _, response = _pool(monkeypatch, status=302, headers={"Location": "/again"})
    with pytest.raises(ValueError, match="redirect limit"):
        _fetch()
    assert factory.call_count == 4
    assert response.close.call_count == 4


def test_response_cap_is_exact(monkeypatch):
    _dns(monkeypatch)
    _, _, response = _pool(monkeypatch, body=b"a" * 1000)
    assert len(_fetch(limit=30)) == 30
    response.close.assert_called_once()


@pytest.mark.parametrize("headers", [
    {"Content-Type": "application/pdf"},
    {"Content-Type": "text/html", "Content-Encoding": "gzip"},
])
def test_nontext_and_compressed_bodies_are_not_read(monkeypatch, headers):
    _dns(monkeypatch)
    _, _, response = _pool(monkeypatch, headers=headers)
    with pytest.raises(ValueError):
        _fetch()
    response.read1.assert_not_called()
    response.close.assert_called_once()


def test_enrichment_caches_and_evicts_without_breaking_extraction(monkeypatch):
    articles._clear_caches_for_tests()
    monkeypatch.setattr(articles, "_MAX_CACHE_ENTRIES", 2)
    fetch = MagicMock(return_value="<p>Target $120</p>")
    monkeypatch.setattr(articles, "fetch_public_text", fetch)
    try:
        for _ in range(3):
            assert articles.fetch_article_body("https://example.org/a") == "Target $120"
        assert fetch.call_count == 1
        articles.fetch_article_body("https://example.org/b")
        articles.fetch_article_body("https://example.org/a")  # keep a recently used
        articles.fetch_article_body("https://example.org/c")
        assert list(articles._BODY_CACHE) == ["https://example.org/a", "https://example.org/c"]
    finally:
        articles._clear_caches_for_tests()


def test_failed_enrichment_is_optional_and_bounds_negative_cache(monkeypatch):
    articles._clear_caches_for_tests()
    monkeypatch.setattr(articles, "_MAX_CACHE_ENTRIES", 2)
    monkeypatch.setattr(articles, "_MAX_TRACKED_HOSTS", 2)
    monkeypatch.setattr(articles, "fetch_public_text", MagicMock(side_effect=ValueError("blocked")))
    try:
        for i in range(5):
            assert articles.fetch_article_body(f"https://host{i}.example/a") is None
        assert len(articles._BODY_CACHE) == len(articles._HOST_FAIL_COUNT) == 2
    finally:
        articles._clear_caches_for_tests()
