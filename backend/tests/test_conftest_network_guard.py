"""Regression tests for the B4-2 conftest hardening: the autouse anti-network
guard + the per-test yfinance breaker reset.

Storia: 6 test flaky ricorrenti (test_ohlcv_service ×5 +
test_nasdaq_analyst_fallback) passavano in isolamento ma fallivano in suite
perché ALTRI test facevano chiamate yfinance/Nasdaq REALI, aprivano il
circuit breaker condiviso (process-global) e i test successivi trovavano
`is_open() == True` → lavoro saltato → assert falliti. Questi test fissano
il contratto delle due fixture autouse in conftest.py.
"""
from __future__ import annotations

import urllib.request

import pytest

from app.services import yfinance_health


# ── anti-network guard ───────────────────────────────────────────────────────

def test_yfinance_ticker_is_blocked() -> None:
    import yfinance

    with pytest.raises(AssertionError, match="real network I/O"):
        yfinance.Ticker("AAPL")


def test_yfinance_download_is_blocked() -> None:
    import yfinance

    with pytest.raises(AssertionError, match="real network I/O"):
        yfinance.download(tickers=["AAPL"])


def test_requests_is_blocked_at_the_adapter() -> None:
    import requests

    # Blocked at HTTPAdapter.send, quindi i mock di alto livello su
    # `requests.get` nei test esistenti non arrivano mai alla guardia.
    with pytest.raises(AssertionError, match="real network I/O"):
        requests.get("http://127.0.0.1:9/never", timeout=1)


def test_httpx_is_blocked_at_the_transport() -> None:
    import httpx

    with pytest.raises(AssertionError, match="real network I/O"):
        httpx.get("http://127.0.0.1:9/never", timeout=1)


def test_urllib_urlopen_is_blocked() -> None:
    with pytest.raises(AssertionError, match="real network I/O"):
        urllib.request.urlopen("http://127.0.0.1:9/never", timeout=1)


def test_higher_level_mocks_still_win(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un test che mocka il seam di servizio non tocca mai la guardia —
    il pattern esistente (patch di yfinance.Ticker / _yf_download) resta valido."""
    import yfinance

    monkeypatch.setattr("yfinance.Ticker", lambda _t: "stub")
    assert yfinance.Ticker("AAPL") == "stub"


# ── per-test breaker reset ───────────────────────────────────────────────────
# I due test qui sotto sono ORDINE-DIPENDENTI di proposito (pytest esegue i
# test di un file nell'ordine di definizione): il primo apre il breaker, il
# secondo verifica che la fixture autouse l'abbia richiuso tra un test e
# l'altro. Prima del fix, lo stato open sarebbe trapelato.

def test_breaker_opened_inside_a_test() -> None:
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("simulated 429 Too Many Requests")
    assert yfinance_health.is_open() is True
    # NESSUN cleanup qui — il punto è proprio verificare l'isolamento autouse.


def test_breaker_state_does_not_leak_into_next_test() -> None:
    assert yfinance_health.is_open() is False
    assert yfinance_health.status()["state"] == "closed"
