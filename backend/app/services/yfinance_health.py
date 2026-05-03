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
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, TypeVar

from loguru import logger

T = TypeVar("T")


# How many recent failures (within WINDOW_SECONDS) trip the breaker.
N_FAILURES = 5
WINDOW_SECONDS = 60.0
# How long the breaker stays open before allowing a probe call.
COOLDOWN_SECONDS = 5 * 60.0


@dataclass
class _State:
    failures: list[float] = field(default_factory=list)   # timestamps
    opened_at: float | None = None
    half_open_in_flight: bool = False


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
        # Cooldown elapsed → allow a single probe (half-open).
        if (time.time() - _state.opened_at) >= COOLDOWN_SECONDS:
            if _state.half_open_in_flight:
                # Another probe is already being attempted — keep blocking others
                return True
            _state.half_open_in_flight = True
            logger.info("[yf-breaker] cooldown elapsed → half-open probe allowed")
            return False
        return True


def record_success() -> None:
    """Mark a successful yfinance call. Closes the breaker if it was half-open."""
    with _lock:
        if _state.opened_at is not None:
            logger.info("[yf-breaker] success after open → closing")
        _state.failures.clear()
        _state.opened_at = None
        _state.half_open_in_flight = False


def record_failure(reason: str = "") -> None:
    """Mark a yfinance failure. May trip the breaker."""
    now = time.time()
    with _lock:
        if _state.half_open_in_flight:
            # Half-open probe failed → re-open with a fresh cooldown
            _state.half_open_in_flight = False
            _state.opened_at = now
            logger.warning(f"[yf-breaker] half-open probe failed ({reason}) → re-open for {COOLDOWN_SECONDS}s")
            return
        _prune_old(now)
        _state.failures.append(now)
        if _state.opened_at is None and len(_state.failures) >= N_FAILURES:
            _state.opened_at = now
            logger.warning(
                f"[yf-breaker] {len(_state.failures)} failures in {WINDOW_SECONDS}s "
                f"({reason}) → OPEN for {COOLDOWN_SECONDS}s"
            )


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
            return {
                "state": "half_open" if _state.half_open_in_flight else "open",
                "opened_at": _state.opened_at,
                "seconds_until_probe": round(seconds_until_probe, 1),
                "failures_in_window": len(_state.failures),
            }
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
