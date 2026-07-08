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
    # `news` is the only op left with a primary + fallback pair after
    # Stooq's OHLCV path was removed (see source_catalog).
    for _ in range(10):
        data_source_metrics.record_failure("yfinance", "news", reason="429")
    for _ in range(10):
        data_source_metrics.record_success("marketaux", "news")
    # news has yfinance failing but marketaux healthy → no gap suggestion
    gaps = data_source_metrics.analyse_gaps()
    assert all(g.op != "news" for g in gaps)


# ─── "unavailable" classification (SAL-1: plan-gated HTTP 403) ────────────


def _single_metric() -> data_source_metrics.SourceMetric:
    snap = data_source_metrics.snapshot()
    assert len(snap) == 1
    return snap[0]


def test_all_403_failures_classified_unavailable() -> None:
    """Plan-gated sources (finnhub upgrades on free tier, twelvedata out of
    plan) fail with 403 on every call — that's a tier limitation, not an
    outage, and must read 'unavailable' instead of pinning the banner."""
    for _ in range(5):
        data_source_metrics.record_failure("finnhub", "upgrades", reason="HTTP 403")
    assert _single_metric().health == "unavailable"


def test_403_client_error_message_variant_matches() -> None:
    """raise_for_status-style reasons ('403 Client Error: Forbidden…') count
    as 403 too — probes and organic call sites word failures differently."""
    data_source_metrics.record_failure(
        "twelvedata", "earnings",
        reason="403 Client Error: Forbidden for url: https://api.twelvedata.com/earnings",
    )
    assert _single_metric().health == "unavailable"


def test_mixed_403_and_other_failures_stay_failing() -> None:
    """A single non-403 failure breaks the plan-gated pattern: the source is
    genuinely erroring, keep the normal classification."""
    data_source_metrics.record_failure("finnhub", "upgrades", reason="HTTP 403")
    data_source_metrics.record_failure("finnhub", "upgrades", reason="timeout")
    assert _single_metric().health == "failing"


def test_403_history_with_recent_success_stays_healthy() -> None:
    """The unavailable override only applies when the classification would
    be failing/degraded — a recovered source reads healthy as before."""
    data_source_metrics.record_failure("finnhub", "upgrades", reason="HTTP 403")
    for _ in range(10):
        data_source_metrics.record_success("finnhub", "upgrades")
    assert _single_metric().health == "healthy"


def test_403_boundary_no_false_positives() -> None:
    """\\b-bounded match: '4033' or '1403ms' must NOT count as 403."""
    data_source_metrics.record_failure("nasdaq", "analyst", reason="HTTP 4033")
    data_source_metrics.record_failure("nasdaq", "analyst", reason="timeout after 1403ms")
    assert _single_metric().health == "failing"


def test_hydrate_legacy_state_seeds_403_counter() -> None:
    """Pre-failure_403 state files: when the LAST failure was a 403, assume
    the (plan-gated) history was homogeneous so the live 'unavailable' fix
    applies without waiting for months of new failures to accrue."""
    data_source_metrics.hydrate_from_dict({
        "finnhub.upgrades": {
            "success": 0, "failure": 42,
            "last_failure_at": 1_700_000_000.0,
            "last_failure_reason": "HTTP 403",
        },
        "yfinance.news": {
            "success": 0, "failure": 7,
            "last_failure_at": 1_700_000_000.0,
            "last_failure_reason": "timeout",
        },
    })
    by_key = {(m.source, m.op): m for m in data_source_metrics.snapshot()}
    assert by_key[("finnhub", "upgrades")].health == "unavailable"
    assert by_key[("yfinance", "news")].health == "failing"
