"""Tests for the yfinance circuit breaker."""
import time

from app.services import yfinance_health


def setup_function() -> None:
    yfinance_health.reset()


def _open_then_elapse_cooldown() -> None:
    """Trip the breaker, then rewind opened_at so the cooldown has elapsed."""
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("simulated 429")
    yfinance_health._states[yfinance_health.LANE_DEFAULT].opened_at = time.time() - yfinance_health.COOLDOWN_SECONDS - 1


def test_half_open_probe_success_closes() -> None:
    """Normal recovery path: after cooldown the granted probe succeeds and
    record_success() closes the breaker."""
    _open_then_elapse_cooldown()
    assert yfinance_health.is_open() is False        # granted the half-open probe
    yfinance_health.record_success()
    assert yfinance_health.is_open() is False         # closed
    assert yfinance_health.status()["state"] == "closed"


def test_half_open_slot_self_expires_when_probe_never_reports() -> None:
    """A caller can be granted the half-open probe (is_open()->False) yet never
    report back via record_success()/record_failure() — e.g. a probe that only
    READS is_open() to decide `skip_yfinance`, or call_protected. The slot must
    NOT leak forever: after HALF_OPEN_PROBE_TIMEOUT it self-expires so a fresh
    probe is allowed and the breaker can recover. (Regression: this used to
    wedge the breaker permanently in half-open.)"""
    _open_then_elapse_cooldown()
    assert yfinance_health.is_open() is False          # first caller granted the probe
    assert yfinance_health.is_open() is True            # slot claimed → others blocked
    # The granted probe is abandoned (never reported) and goes stale.
    yfinance_health._states[yfinance_health.LANE_DEFAULT].half_open_at = (
        time.time() - yfinance_health.HALF_OPEN_PROBE_TIMEOUT - 1
    )
    assert yfinance_health.is_open() is False           # self-expired → fresh probe allowed


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
    # Absolute unblock instant exposed for the UI countdown — must be in the
    # future and consistent with the relative figure.
    assert s["blocked_until"] > time.time()
    assert s["blocked_until"] == s["opened_at"] + yfinance_health.COOLDOWN_SECONDS


def test_status_half_open_exposes_probe_deadline() -> None:
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("x")
    # Rewind so the cooldown has elapsed, then grant a half-open probe.
    yfinance_health._states[yfinance_health.LANE_DEFAULT].opened_at = time.time() - yfinance_health.COOLDOWN_SECONDS - 1
    assert yfinance_health.is_open() is False  # grants the half-open probe
    s = yfinance_health.status()
    assert s["state"] == "half_open"
    # Cooldown already elapsed → unblock instant is in the past.
    assert s["blocked_until"] <= time.time()
    # Probe deadline is in the future (when a stalled probe is retried).
    assert s["probe_deadline"] > time.time()


# ─── Lane isolation (incident 2026-07-24) ──────────────────────────────────
# ~100 symbols (AMZN, MSFT among them) silently lost a WEEK of daily bars
# because one shared breaker was tripped by the every-75s intraday quote sweep
# and the OHLCV fetch then skipped its batches on is_open(). Yahoo was serving
# those bars fine the whole time. These tests pin the isolation that prevents
# a repeat: the cheap-to-lose lane must never gate the permanent-data lane.


def test_quote_flood_does_not_open_the_ohlcv_lane() -> None:
    """THE regression test for the July 2026 data-loss incident."""
    for _ in range(yfinance_health.N_FAILURES * 2):
        yfinance_health.record_failure("429", lane=yfinance_health.LANE_QUOTES)

    assert yfinance_health.is_open(yfinance_health.LANE_QUOTES) is True
    # The bar fetch must remain free to run — this is the whole point.
    assert yfinance_health.is_open(yfinance_health.LANE_OHLCV) is False
    assert yfinance_health.is_open(yfinance_health.LANE_DEFAULT) is False


def test_lanes_recover_independently() -> None:
    """Closing one lane must not close another that is legitimately open."""
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("429", lane=yfinance_health.LANE_QUOTES)
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("boom", lane=yfinance_health.LANE_OHLCV)
    assert yfinance_health.is_open(yfinance_health.LANE_QUOTES) is True
    assert yfinance_health.is_open(yfinance_health.LANE_OHLCV) is True

    yfinance_health.record_success(yfinance_health.LANE_OHLCV)
    assert yfinance_health.is_open(yfinance_health.LANE_OHLCV) is False
    assert yfinance_health.is_open(yfinance_health.LANE_QUOTES) is True


def test_status_reports_worst_lane_and_keeps_its_legacy_shape() -> None:
    """The Salute UI reads the top-level keys, so an open lane must surface
    there even though state is now per-lane — plus a `lanes` breakdown."""
    for _ in range(yfinance_health.N_FAILURES):
        yfinance_health.record_failure("429", lane=yfinance_health.LANE_QUOTES)

    st = yfinance_health.status()
    assert st["state"] == "open"                     # headline = worst lane
    assert "blocked_until" in st                     # legacy key still present
    assert st["lanes"][yfinance_health.LANE_QUOTES]["state"] == "open"
    assert st["lanes"][yfinance_health.LANE_OHLCV]["state"] == "closed"
    # Asking for a specific lane returns just that lane, no `lanes` key.
    assert yfinance_health.status(yfinance_health.LANE_OHLCV)["state"] == "closed"
