"""Tests for the yfinance circuit breaker."""
from app.services import yfinance_health


def setup_function() -> None:
    yfinance_health.reset()


def test_breaker_starts_closed() -> None:
    assert not yfinance_health.is_open()


def test_breaker_opens_after_n_failures() -> None:
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("simulated 429")
    assert yfinance_health.is_open()


def test_breaker_does_not_open_below_threshold() -> None:
    for _ in range(yfinance_health.N_FAILURES - 1):
        yfinance_health.record_failure("simulated 429")
    assert not yfinance_health.is_open()


def test_record_success_clears_failures() -> None:
    yfinance_health.record_failure("x")
    yfinance_health.record_failure("x")
    yfinance_health.record_success()
    # Add more failures, but the cleared count means we won't trip yet
    for _ in range(yfinance_health.N_FAILURES - 1):
        yfinance_health.record_failure("x")
    assert not yfinance_health.is_open()


def test_is_rate_limit_error_recognises_429() -> None:
    err = Exception("429 Client Error: Too Many Requests")
    assert yfinance_health.is_rate_limit_error(err) is True


def test_is_rate_limit_error_recognises_json_decode() -> None:
    err = Exception("Expecting value: line 1 column 1 (char 0)")
    assert yfinance_health.is_rate_limit_error(err) is True


def test_is_rate_limit_error_ignores_delisted_tickers() -> None:
    err = Exception("possibly delisted; no price data found")
    assert yfinance_health.is_rate_limit_error(err) is False


def test_status_reflects_open_state() -> None:
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("x")
    s = yfinance_health.status()
    assert s["state"] == "open"
    assert s["seconds_until_probe"] > 0
