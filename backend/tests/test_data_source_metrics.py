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


# ─── outcome-of-last-batch classifier (SAL-2) ─────────────────────────────
# Health keys on the LAST batch's verdict — not on a 60s decaying failure
# window mixed with a non-decaying lifetime rate (the old flip-flop: a
# source read "failing" for a minute after a failure, then snapped back to
# whatever the frozen historical average said).


def test_last_call_failure_classifies_failing_regardless_of_history() -> None:
    for _ in range(97):
        data_source_metrics.record_success("yfinance", "market_cap")
    data_source_metrics.record_failure("yfinance", "market_cap", reason="429")
    snap = {(m.source, m.op): m for m in data_source_metrics.snapshot()}
    m = snap[("yfinance", "market_cap")]
    assert m.health == "failing"          # last batch failed → failing
    assert m.success_rate > 0.9           # rate is informational only


def test_success_after_failures_recovers_to_healthy_immediately() -> None:
    """No time decay: one successful batch flips the source back to healthy
    even if the lifetime rate is terrible."""
    for _ in range(9):
        data_source_metrics.record_failure("yfinance", "news", reason="timeout")
    data_source_metrics.record_success("yfinance", "news")
    snap = data_source_metrics.snapshot()
    assert snap[0].health == "healthy"
    assert snap[0].success_rate == 0.1


def test_record_batch_partial_classifies_degraded() -> None:
    """A batch with BOTH successes and failures (the ohlcv per-run shape)
    reads 'partial' → degraded, not whichever record landed last."""
    data_source_metrics.record_batch(
        "yfinance", "ohlcv", succeeded=950, failed=49,
        reason="49 tickers without data",
    )
    snap = data_source_metrics.snapshot()
    m = snap[0]
    assert m.health == "degraded"
    assert m.success == 950 and m.failure == 49
    assert "49 tickers" in (m.last_failure_reason or "")


def test_record_batch_all_failed_classifies_failing() -> None:
    data_source_metrics.record_batch(
        "yfinance", "ohlcv", succeeded=0, failed=999, reason="yf.download crashed"
    )
    assert data_source_metrics.snapshot()[0].health == "failing"


def test_record_batch_all_ok_classifies_healthy() -> None:
    data_source_metrics.record_batch("yfinance", "ohlcv", succeeded=999, failed=0)
    assert data_source_metrics.snapshot()[0].health == "healthy"


def test_record_batch_empty_is_noop() -> None:
    data_source_metrics.record_batch("yfinance", "ohlcv", succeeded=0, failed=0)
    assert data_source_metrics.snapshot() == []


def test_record_batch_ok_after_partial_recovers() -> None:
    """The verdict is per-BATCH: a clean run right after a partial one flips
    the source back to healthy."""
    data_source_metrics.record_batch("yfinance", "ohlcv", succeeded=500, failed=499)
    assert data_source_metrics.snapshot()[0].health == "degraded"
    data_source_metrics.record_batch("yfinance", "ohlcv", succeeded=999, failed=0)
    assert data_source_metrics.snapshot()[0].health == "healthy"


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


def test_hydrate_legacy_state_derives_verdict_from_event_order() -> None:
    """State files predating `last_batch`: the classifier approximates the
    last-batch verdict from the newest event's timestamp."""
    data_source_metrics.hydrate_from_dict({
        "yfinance.ohlcv": {   # success is the NEWEST event → ok → healthy
            "success": 100, "failure": 5,
            "last_success_at": 1_700_000_100.0,
            "last_failure_at": 1_700_000_000.0,
            "last_failure_reason": "timeout",
        },
        "fred.macro": {       # failure is the NEWEST event → failed → failing
            "success": 100, "failure": 5,
            "last_success_at": 1_700_000_000.0,
            "last_failure_at": 1_700_000_100.0,
            "last_failure_reason": "timeout",
        },
    })
    by_key = {(m.source, m.op): m for m in data_source_metrics.snapshot()}
    assert by_key[("yfinance", "ohlcv")].health == "healthy"
    assert by_key[("fred", "macro")].health == "failing"


def test_last_batch_verdict_survives_serialize_hydrate_roundtrip() -> None:
    data_source_metrics.record_batch("yfinance", "ohlcv", succeeded=10, failed=3)
    data = data_source_metrics._serialize_locked()
    data_source_metrics.reset()
    data_source_metrics.hydrate_from_dict(data)
    assert data_source_metrics.snapshot()[0].health == "degraded"


# ─── staleness decay (SAL-2: source_catalog cadence downgrade) ────────────


def _catalog_health(source: str, op: str) -> str:
    from app.services import source_catalog

    for s in source_catalog.full_snapshot():
        if (s.source, s.op) == (source, op):
            return s.health
    raise AssertionError(f"{source}.{op} not in catalog snapshot")


def _age_last_success(source: str, op: str, seconds: float) -> None:
    """Backdate the counter's last success — simulates a silent stop."""
    key = f"{source}.{op}"
    c = data_source_metrics._counters[key]
    c.last_success_at = (c.last_success_at or 0.0) - seconds


def test_healthy_source_past_cadence_reads_stale() -> None:
    """A primary (cadence ~6h) with a success older than cadence × grace is
    'stale' — the frozen-green dead-probe mode, distinct from 'failing'."""
    data_source_metrics.record_success("yfinance", "ohlcv")
    _age_last_success("yfinance", "ohlcv", 10 * 3600)   # 10h > 6h × 1.5
    assert _catalog_health("yfinance", "ohlcv") == "stale"


def test_healthy_source_within_cadence_stays_healthy() -> None:
    data_source_metrics.record_success("yfinance", "ohlcv")
    _age_last_success("yfinance", "ohlcv", 3 * 3600)    # 3h < 6h × 1.5
    assert _catalog_health("yfinance", "ohlcv") == "healthy"


def test_weekly_scheduled_source_uses_weekly_cadence() -> None:
    """SEC/Dataroma cron weekly: 3 days old is fine, 12 days is stale."""
    data_source_metrics.record_success("dataroma", "holdings")
    _age_last_success("dataroma", "holdings", 3 * 86400)
    assert _catalog_health("dataroma", "holdings") == "healthy"
    _age_last_success("dataroma", "holdings", 9 * 86400)   # tot 12d > 7d × 1.5
    assert _catalog_health("dataroma", "holdings") == "stale"


def test_failing_source_stays_failing_not_stale() -> None:
    """Staleness only downgrades HEALTHY sources — a failing source keeps its
    (more severe, more actionable) verdict."""
    data_source_metrics.record_success("yfinance", "ohlcv")
    data_source_metrics.record_failure("yfinance", "ohlcv", reason="boom")
    _age_last_success("yfinance", "ohlcv", 10 * 3600)
    assert _catalog_health("yfinance", "ohlcv") == "failing"


def test_idle_source_never_stale() -> None:
    """No calls at all → 'idle' (there is no last_success_at to age)."""
    assert _catalog_health("dataroma", "holdings") == "idle"


def test_fallback_without_cadence_never_stale() -> None:
    """On-demand fallbacks (marketaux) have no expected cadence — a months-old
    success is normal, not an incident."""
    data_source_metrics.record_success("marketaux", "news")
    _age_last_success("marketaux", "news", 30 * 86400)
    assert _catalog_health("marketaux", "news") == "healthy"
