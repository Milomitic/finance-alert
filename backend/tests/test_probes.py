"""Probe orchestrator tests.

We mock each probe function rather than the upstream itself — the
orchestrator's only contract is: "run each probe, isolate failures,
respect the breaker for yfinance probes". Real upstream behavior is
tested by integration only (manual smoke).
"""
from unittest.mock import patch

import pytest

from app.services import data_source_metrics, probes, yfinance_health


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Each test starts from a clean counter state."""
    data_source_metrics.reset()
    yfinance_health.reset()
    yield
    data_source_metrics.reset()
    yfinance_health.reset()


def test_record_success_helper_writes_to_metrics():
    probes._record("yfinance", "live_quote", ok=True)
    snap = data_source_metrics.snapshot()
    by_key = {(m.source, m.op): m for m in snap}
    assert by_key[("yfinance", "live_quote")].success == 1
    assert by_key[("yfinance", "live_quote")].failure == 0


def test_record_failure_helper_writes_to_metrics():
    probes._record("marketaux", "news", ok=False, reason="HTTP 503")
    snap = data_source_metrics.snapshot()
    by_key = {(m.source, m.op): m for m in snap}
    assert by_key[("marketaux", "news")].failure == 1
    assert "503" in (by_key[("marketaux", "news")].last_failure_reason or "")


def test_run_fast_probes_invokes_all_probes_when_breaker_closed():
    """With breaker closed, every probe in FAST_PROBES runs once."""
    calls: list[str] = []

    def make_stub(name: str):
        def _stub():
            calls.append(name)
        _stub.__name__ = f"probe_{name}"
        return _stub

    fake_probes = [
        make_stub("yfinance_live_quote"),
        make_stub("yfinance_market_cap"),
        make_stub("stooq_ohlcv"),
        make_stub("finnhub_earnings"),
    ]
    with patch.object(probes, "FAST_PROBES", fake_probes):
        probes.run_fast_probes()
    assert calls == [
        "yfinance_live_quote", "yfinance_market_cap",
        "stooq_ohlcv", "finnhub_earnings",
    ]


def test_run_fast_probes_skips_yfinance_when_breaker_open(monkeypatch):
    """When the circuit breaker is open we must not pile more failed
    yfinance calls onto it — only non-yfinance probes should run."""
    monkeypatch.setattr(yfinance_health, "is_open", lambda: True)

    calls: list[str] = []

    def make_stub(name: str):
        def _stub():
            calls.append(name)
        _stub.__name__ = f"probe_{name}"
        return _stub

    fake_probes = [
        make_stub("yfinance_live_quote"),
        make_stub("yfinance_market_cap"),
        make_stub("stooq_ohlcv"),
        make_stub("finnhub_earnings"),
    ]
    with patch.object(probes, "FAST_PROBES", fake_probes):
        probes.run_fast_probes()
    # Only non-yfinance probes executed.
    assert calls == ["stooq_ohlcv", "finnhub_earnings"]


def test_run_fast_probes_isolates_per_probe_exceptions():
    """A probe that crashes must NOT skip the probes after it."""
    calls: list[str] = []

    def crasher():
        calls.append("crasher")
        raise RuntimeError("boom")
    crasher.__name__ = "probe_crasher"

    def good():
        calls.append("good")
    good.__name__ = "probe_good"

    with patch.object(probes, "FAST_PROBES", [crasher, good]):
        probes.run_fast_probes()  # must not propagate the RuntimeError
    assert calls == ["crasher", "good"]


def test_individual_probe_records_failure_on_upstream_exception(monkeypatch):
    """Verify the per-probe contract: when the upstream call raises,
    the probe records a failure and does NOT propagate the exception."""
    import yfinance as yf

    class BoomTicker:
        def __init__(self, _t):
            pass

        @property
        def fast_info(self):
            raise RuntimeError("upstream dead")

    monkeypatch.setattr(yf, "Ticker", BoomTicker)
    # The probe must swallow the exception
    probes.probe_yfinance_live_quote()
    snap = data_source_metrics.snapshot()
    by_key = {(m.source, m.op): m for m in snap}
    assert by_key[("yfinance", "live_quote")].failure == 1
    assert "upstream dead" in (
        by_key[("yfinance", "live_quote")].last_failure_reason or ""
    )


def test_individual_probe_records_success_on_valid_response(monkeypatch):
    """Verify the per-probe contract: when the upstream returns a valid
    payload, the probe records a success."""
    import yfinance as yf

    class OkTicker:
        def __init__(self, _t):
            pass

        @property
        def fast_info(self):
            class FI:
                last_price = 200.5
            return FI()

    monkeypatch.setattr(yf, "Ticker", OkTicker)
    probes.probe_yfinance_live_quote()
    snap = data_source_metrics.snapshot()
    by_key = {(m.source, m.op): m for m in snap}
    assert by_key[("yfinance", "live_quote")].success == 1
    assert by_key[("yfinance", "live_quote")].failure == 0
