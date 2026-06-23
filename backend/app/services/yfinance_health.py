"""Yahoo Finance circuit breaker.

Yahoo aggressively rate-limits or IP-blocks heavy yfinance traffic. Symptoms:
- HTTP 429 ("Too Many Requests")
- HTML body returned where JSON expected → JSONDecodeError ("Expecting value")
- yfinance prints "possibly delisted" / "no price data found"
- Fast endpoints silently return None for every key

The breaker keeps a sliding window of the last few outcomes. If too many
consecutive failures occur it OPENS for a cooldown period: callers can check
`is_open()` and skip yfinance entirely (or fall back to another source).

Closed → Open transition: ≥ N_FAILURES failures in the last WINDOW seconds.
Open → Half-Open after COOLDOWN_SECONDS: a single probe call is allowed.
Half-Open → Closed on success, → Open on failure.

This is in-process (single uvicorn worker assumption — fine for local-first).
"""
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Callable, TypeVar

from loguru import logger

from app.core import breaker_state

T = TypeVar("T")

# Persist the yfinance breaker's open state across restarts (the 4 fallback
# breakers already do this via breaker_state). Reuses the same JSON store under
# this key so an OPEN breaker stays open — with its remaining cooldown — after a
# kill+restart instead of reopening on the first call and re-discovering the
# rate-limit. Persistence is skipped under pytest to avoid touching the file.
_BREAKER_KEY = "yfinance"


# How many recent failures (within WINDOW_SECONDS) trip the breaker.
N_FAILURES = 5
WINDOW_SECONDS = 60.0
# How long the breaker stays open before allowing a probe call.
COOLDOWN_SECONDS = 5 * 60.0
# How long a granted half-open probe may stay "in flight" before it's treated
# as ABANDONED and a fresh probe is allowed. The half-open slot is meant for a
# single caller that reports back (record_success/record_failure), but some
# callers only READ is_open() to gate (probes' skip_yfinance, call_protected)
# and never report — which would otherwise leak the slot and wedge the breaker
# in half-open forever. A real probe (one yfinance call) resolves in well under
# this window, so a slot older than it is provably abandoned. (Bug fix 2026-05.)
HALF_OPEN_PROBE_TIMEOUT = 30.0


@dataclass
class _State:
    failures: list[float] = field(default_factory=list)   # timestamps
    opened_at: float | None = None
    half_open_in_flight: bool = False
    half_open_at: float | None = None   # when the current half-open probe was granted


_state = _State()
_lock = Lock()


def _prune_old(now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    _state.failures = [t for t in _state.failures if t >= cutoff]


def is_open() -> bool:
    """Return True if the breaker is currently OPEN (callers should skip yfinance)."""
    with _lock:
        if _state.opened_at is None:
            return False
        now = time.time()
        # Cooldown elapsed → allow a single probe (half-open).
        if (now - _state.opened_at) >= COOLDOWN_SECONDS:
            # A probe is "in flight" only if it was granted RECENTLY. If the
            # granted caller never reported back within HALF_OPEN_PROBE_TIMEOUT
            # (a leaked slot — e.g. a probe that only gated on is_open()), the
            # slot is abandoned: grant a fresh probe so the breaker can recover
            # instead of wedging in half-open forever.
            if (
                _state.half_open_in_flight
                and _state.half_open_at is not None
                and (now - _state.half_open_at) < HALF_OPEN_PROBE_TIMEOUT
            ):
                return True  # a recent probe is genuinely in flight — block others
            if _state.half_open_in_flight:
                logger.warning(
                    "[yf-breaker] half-open probe abandoned (no outcome in "
                    f"{HALF_OPEN_PROBE_TIMEOUT}s) → granting a fresh probe"
                )
            _state.half_open_in_flight = True
            _state.half_open_at = now
            logger.info("[yf-breaker] cooldown elapsed → half-open probe allowed")
            return False
        return True


def _persist_open(opened_at: float, reason: str) -> None:
    """Persist the breaker-open timestamp so it survives a restart. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    until = datetime.fromtimestamp(opened_at, UTC) + timedelta(seconds=COOLDOWN_SECONDS)
    breaker_state.save(_BREAKER_KEY, until, reason=(reason or "")[:200])


def _persist_clear() -> None:
    """Drop the persisted open state when the breaker closes. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    breaker_state.clear(_BREAKER_KEY)


def load_from_disk() -> bool:
    """At boot, restore an OPEN breaker from disk (with its remaining cooldown).
    Returns True if a still-open breaker was restored. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    until = breaker_state.load(_BREAKER_KEY)  # None if absent or cooldown elapsed
    if until is None:
        return False
    with _lock:
        _state.opened_at = (until - timedelta(seconds=COOLDOWN_SECONDS)).timestamp()
    logger.info(f"[yf-breaker] restored OPEN from disk (cooldown until {until.isoformat()})")
    return True


def record_success() -> None:
    """Mark a successful yfinance call. Closes the breaker if it was half-open."""
    with _lock:
        was_open = _state.opened_at is not None
        if was_open:
            logger.info("[yf-breaker] success after open → closing")
        _state.failures.clear()
        _state.opened_at = None
        _state.half_open_in_flight = False
        _state.half_open_at = None
    if was_open:
        _persist_clear()  # only touch disk on a real open→closed transition


def record_failure(reason: str = "") -> None:
    """Mark a yfinance failure. May trip the breaker."""
    now = time.time()
    opened_now = False
    with _lock:
        if _state.half_open_in_flight:
            # Half-open probe failed → re-open with a fresh cooldown
            _state.half_open_in_flight = False
            _state.half_open_at = None
            _state.opened_at = now
            opened_now = True
            logger.warning(f"[yf-breaker] half-open probe failed ({reason}) → re-open for {COOLDOWN_SECONDS}s")
        else:
            _prune_old(now)
            _state.failures.append(now)
            if _state.opened_at is None and len(_state.failures) >= N_FAILURES:
                _state.opened_at = now
                opened_now = True
                logger.warning(
                    f"[yf-breaker] {len(_state.failures)} failures in {WINDOW_SECONDS}s "
                    f"({reason}) → OPEN for {COOLDOWN_SECONDS}s"
                )
    if opened_now:
        _persist_open(now, reason)


def is_rate_limit_error(exc: BaseException) -> bool:
    """Heuristic: True iff the exception is one of the yfinance rate-limit
    fingerprints we want to count as a breaker failure."""
    s = str(exc)
    if "429" in s or "Too Many Requests" in s:
        return True
    # Yahoo returns HTML/Cloudflare challenge → JSON decode error
    if "Expecting value" in s or "JSONDecodeError" in s:
        return True
    if "delisted" in s.lower() and "no price data" in s.lower():
        # This one is per-ticker noise, not a global rate-limit signal.
        return False
    return False


def call_protected(name: str, fn: Callable[[], T], default: T | None = None) -> T | None:
    """Run `fn()`, recording outcome to the breaker. Returns `default` if the
    breaker is open or the call raises a rate-limit-type error.

    Use for yfinance calls where a partial failure should be transparent to
    the caller (e.g. micro data — if breaker is open, return MicroData()).
    """
    if is_open():
        return default
    try:
        out = fn()
    except Exception as exc:  # noqa: BLE001
        if is_rate_limit_error(exc):
            record_failure(f"{name}: {exc}")
            return default
        # Other exceptions don't trip the breaker but still bubble up so the
        # caller can decide.
        raise
    # We don't record success here for individual sub-calls because yfinance
    # can return a structurally valid empty payload even when rate-limited;
    # callers that get a "real" response (e.g. non-empty DataFrame) should
    # call record_success() explicitly.
    return out


def status() -> dict:
    """Diagnostic snapshot for logging / health endpoint."""
    with _lock:
        now = time.time()
        _prune_old(now)
        if _state.opened_at is not None:
            seconds_until_probe = max(0.0, COOLDOWN_SECONDS - (now - _state.opened_at))
            out = {
                "state": "half_open" if _state.half_open_in_flight else "open",
                "opened_at": _state.opened_at,
                "seconds_until_probe": round(seconds_until_probe, 1),
                # Absolute epoch (UTC seconds) when the cooldown lifts and a
                # half-open probe is allowed. The UI counts down against this so
                # the figure stays accurate between health polls. In half-open
                # this is already in the past (cooldown elapsed → probing now).
                "blocked_until": _state.opened_at + COOLDOWN_SECONDS,
                "failures_in_window": len(_state.failures),
            }
            if _state.half_open_in_flight and _state.half_open_at is not None:
                # When the in-flight probe is treated as abandoned and a fresh
                # probe is granted — the UI shows this as the half-open deadline.
                out["probe_deadline"] = _state.half_open_at + HALF_OPEN_PROBE_TIMEOUT
            return out
        return {
            "state": "closed",
            "failures_in_window": len(_state.failures),
        }


def reset() -> None:
    """For tests."""
    with _lock:
        _state.failures.clear()
        _state.opened_at = None
        _state.half_open_in_flight = False
        _state.half_open_at = None
