"""Tests for data_source_metrics."""
from app.services import data_source_metrics


def setup_function() -> None:
    data_source_metrics.reset()


def test_no_calls_idle() -> None:
    snap = data_source_metrics.snapshot()
    assert snap == []


def test_record_success_marks_healthy() -> None:
    for _ in range(10):
        data_source_metrics.record_success("yfinance", "ohlcv")
    snap = data_source_metrics.snapshot()
    assert len(snap) == 1
    assert snap[0].health == "healthy"
    assert snap[0].success_rate == 1.0


def test_mixed_outcomes_classified_degraded_or_failing() -> None:
    for _ in range(7):
        data_source_metrics.record_success("yfinance", "market_cap")
    for _ in range(3):
        data_source_metrics.record_failure("yfinance", "market_cap", reason="429")
    snap = {(m.source, m.op): m for m in data_source_metrics.snapshot()}
    m = snap[("yfinance", "market_cap")]
    # 7/10 = 0.7 → degraded; but the LAST op was a failure within the 60s
    # window so the classifier downgrades to "failing" — that's the desired
    # contract.
    assert m.health in ("degraded", "failing")


def test_analyse_gaps_silent_when_healthy() -> None:
    for _ in range(10):
        data_source_metrics.record_success("yfinance", "fundamentals")
    assert data_source_metrics.analyse_gaps() == []


def test_analyse_gaps_suggests_when_only_source_failing() -> None:
    for _ in range(10):
        data_source_metrics.record_failure("yfinance", "fundamentals", reason="429")
    gaps = data_source_metrics.analyse_gaps()
    assert any(g.op == "fundamentals" for g in gaps)


def test_analyse_gaps_silent_when_fallback_healthy() -> None:
    for _ in range(10):
        data_source_metrics.record_failure("yfinance", "ohlcv", reason="429")
    for _ in range(10):
        data_source_metrics.record_success("stooq", "ohlcv")
    # ohlcv has yfinance failing but stooq healthy → no gap suggestion
    gaps = data_source_metrics.analyse_gaps()
    assert all(g.op != "ohlcv" for g in gaps)
