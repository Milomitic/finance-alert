"""SAL-1 scraper instrumentation: the organic (non-probe) call sites of
Dataroma, SEC EDGAR 13F and Nasdaq pre-market must feed data_source_metrics,
so the Salute "Fonti dati" card reflects the real cron traffic (the 13F
crons died for months while the card stayed green off probe pings alone).

Network is faked at the lowest seam each service uses (requests.get /
urllib.request.urlopen) — below any service logic, above the conftest
anti-network guard.
"""
import io
import json
import urllib.request
from types import SimpleNamespace

import pytest

from app.services import data_source_metrics


@pytest.fixture(autouse=True)
def _clean_metrics():
    data_source_metrics.reset()
    yield
    data_source_metrics.reset()


def _metric(source: str, op: str) -> data_source_metrics.SourceMetric | None:
    for m in data_source_metrics.snapshot():
        if (m.source, m.op) == (source, op):
            return m
    return None


# ─── Dataroma (institutional_scraper._http_get) ──────────────────────────


def _resp(status_code: int = 200, text: str = "<html></html>") -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, text=text)


def test_dataroma_success_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import institutional_scraper

    monkeypatch.setattr(
        institutional_scraper.requests, "get", lambda *a, **k: _resp(200)
    )
    assert institutional_scraper._http_get("https://www.dataroma.com/m/managers.php")
    m = _metric("dataroma", "holdings")
    assert m is not None and m.success == 1 and m.failure == 0


def test_dataroma_http_error_recorded_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import institutional_scraper

    monkeypatch.setattr(
        institutional_scraper.requests, "get", lambda *a, **k: _resp(503)
    )
    assert institutional_scraper._http_get("https://www.dataroma.com/x") is None
    m = _metric("dataroma", "holdings")
    assert m is not None and m.failure == 1
    assert "503" in (m.last_failure_reason or "")


def test_dataroma_network_exception_recorded_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import institutional_scraper

    def _boom(*a, **k):
        raise ConnectionError("dns fail")

    monkeypatch.setattr(institutional_scraper.requests, "get", _boom)
    assert institutional_scraper._http_get("https://www.dataroma.com/x") is None
    m = _metric("dataroma", "holdings")
    assert m is not None and m.failure == 1


def test_dataroma_in_known_sources_catalog() -> None:
    """The catalog entry makes the source visible on the Salute card even
    while idle (between weekly crons)."""
    from app.services import source_catalog

    specs = {(s.source, s.op) for s in source_catalog.KNOWN_SOURCES}
    assert ("dataroma", "holdings") in specs
    snap = {(s.source, s.op) for s in source_catalog.full_snapshot()}
    assert ("dataroma", "holdings") in snap


# ─── SEC EDGAR 13F (sec_13f_scraper._http_get_json/_http_get_text) ───────


def test_sec_13f_json_success_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import sec_13f_scraper

    monkeypatch.setattr(
        sec_13f_scraper.requests, "get",
        lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: {"cik": 1}),
    )
    assert sec_13f_scraper._http_get_json("https://data.sec.gov/x.json") == {"cik": 1}
    m = _metric("sec_13f", "filings")
    assert m is not None and m.success == 1


def test_sec_13f_text_http_error_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import sec_13f_scraper

    monkeypatch.setattr(
        sec_13f_scraper.requests, "get", lambda *a, **k: _resp(429)
    )
    assert sec_13f_scraper._http_get_text("https://www.sec.gov/x.xml") is None
    m = _metric("sec_13f", "filings")
    assert m is not None and m.failure == 1
    assert "429" in (m.last_failure_reason or "")


# ─── Nasdaq pre-market (premarket_service._nasdaq_premarket_volume) ──────


class _FakeUrlopen:
    """Context manager mimicking urllib.request.urlopen's response."""

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return io.BytesIO(self._body)

    def __exit__(self, *exc):
        return False


def test_nasdaq_premarket_organic_success_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "data": {
            "marketStatus": "Pre-Market",
            "primaryData": {"volume": "2,578,531.09"},
        }
    }
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *a, **k: _FakeUrlopen(payload)
    )
    from app.services import premarket_service

    vol = premarket_service._nasdaq_premarket_volume("AAPL")
    assert vol == 2578531
    m = _metric("nasdaq", "premarket")
    assert m is not None and m.success == 1 and m.failure == 0


def test_nasdaq_premarket_outside_window_is_still_source_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside the pre-market window the endpoint answers fine with regular
    data — semantic no-data, NOT a source failure."""
    payload = {"data": {"marketStatus": "Open", "primaryData": {"volume": "1"}}}
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *a, **k: _FakeUrlopen(payload)
    )
    from app.services import premarket_service

    assert premarket_service._nasdaq_premarket_volume("AAPL") is None
    m = _metric("nasdaq", "premarket")
    assert m is not None and m.success == 1 and m.failure == 0


def test_nasdaq_premarket_network_error_recorded_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    def _boom(*a, **k):
        raise urllib.error.URLError("blocked")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    from app.services import premarket_service

    assert premarket_service._nasdaq_premarket_volume("AAPL") is None
    m = _metric("nasdaq", "premarket")
    assert m is not None and m.failure == 1 and m.success == 0
