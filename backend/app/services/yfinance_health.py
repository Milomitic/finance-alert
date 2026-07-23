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

── LANES (2026-07-24) ────────────────────────────────────────────────────────
State is kept PER LANE, not globally. A single shared breaker caused a real
data-loss incident: `live_movers_sweep` polls quotes every 75s over 200
tickers, Yahoo 429'd it, five failures tripped the ONE breaker, and the
nightly OHLCV fetch — which was not rate-limited at all — then skipped its
whole batch on `is_open()`. Roughly 100 symbols (AMZN and MSFT among them)
silently stopped receiving daily bars for a week while every scan still
reported "success". A manual refetch pulled those same bars in ~3 seconds,
proving the data had been available the entire time.

The lanes therefore reflect COST OF LOSS, not just traffic:

- LANE_QUOTES — intraday quotes. High volume, ephemeral: a missed quote is
  re-fetched seconds later, so this lane is allowed to trip often.
- LANE_OHLCV  — daily bars. Low volume, PERMANENT: a bar not captured is a
  hole in the chart until someone notices. It must never be blocked by the
  quote flood.
- LANE_DEFAULT — everything else (fundamentals, market cap, probes).

Keep the noisy, cheap-to-lose traffic OFF the lane that carries data you
cannot re-derive.
"""
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TypeVar

from loguru import logger

from app.core import breaker_state

T = TypeVar("T")

# Lane identifiers — see the module docstring for why these are separate.
LANE_DEFAULT = "default"
LANE_QUOTES = "quotes"
LANE_OHLCV = "ohlcv"
KNOWN_LANES = (LANE_DEFAULT, LANE_QUOTES, LANE_OHLCV)

# Persist the yfinance breaker's open state across restarts (the 4 fallback
# breakers already do this via breaker_state). Reuses the same JSON store under
# this key so an OPEN breaker stays open — with its remaining cooldown — after a
# kill+restart instead of reopening on the first call and re-discovering the
# rate-limit. Persistence is skipped under pytest to avoid touching the file.
# The default lane keeps the bare key so previously-persisted state still loads.
_BREAKER_KEY = "yfinance"


def _key(lane: str) -> str:
    return _BREAKER_KEY if lane == LANE_DEFAULT else f"{_BREAKER_KEY}:{lane}"


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


_states: dict[str, _State] = {lane: _State() for lane in KNOWN_LANES}
_lock = Lock()


def _st(lane: str) -> _State:
    """Return (creating if needed) the state for `lane`. Call under _lock."""
    st = _states.get(lane)
    if st is None:
        st = _State()
        _states[lane] = st
    return st


def _prune_old(st: _State, now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    st.failures = [t for t in st.failures if t >= cutoff]


def is_open(lane: str = LANE_DEFAULT) -> bool:
    """Return True if `lane`'s breaker is OPEN (callers should skip yfinance)."""
    with _lock:
        st = _st(lane)
        if st.opened_at is None:
            return False
        now = time.time()
        # Cooldown elapsed → allow a single probe (half-open).
        if (now - st.opened_at) >= COOLDOWN_SECONDS:
            # A probe is "in flight" only if it was granted RECENTLY. If the
            # granted caller never reported back within HALF_OPEN_PROBE_TIMEOUT
            # (a leaked slot — e.g. a probe that only gated on is_open()), the
            # slot is abandoned: grant a fresh probe so the breaker can recover
            # instead of wedging in half-open forever.
            if (
                st.half_open_in_flight
                and st.half_open_at is not None
                and (now - st.half_open_at) < HALF_OPEN_PROBE_TIMEOUT
            ):
                return True  # a recent probe is genuinely in flight — block others
            if st.half_open_in_flight:
                logger.warning(
                    f"[yf-breaker:{lane}] half-open probe abandoned (no outcome in "
                    f"{HALF_OPEN_PROBE_TIMEOUT}s) → granting a fresh probe"
                )
            st.half_open_in_flight = True
            st.half_open_at = now
            logger.info(f"[yf-breaker:{lane}] cooldown elapsed → half-open probe allowed")
            return False
        return True


def _persist_open(lane: str, opened_at: float, reason: str) -> None:
    """Persist the breaker-open timestamp so it survives a restart. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    until = datetime.fromtimestamp(opened_at, UTC) + timedelta(seconds=COOLDOWN_SECONDS)
    breaker_state.save(_key(lane), until, reason=(reason or "")[:200])


def _persist_clear(lane: str) -> None:
    """Drop the persisted open state when the breaker closes. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    breaker_state.clear(_key(lane))


def load_from_disk() -> bool:
    """At boot, restore any OPEN lane from disk (with its remaining cooldown).
    Returns True if at least one still-open breaker was restored. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    restored = False
    for lane in KNOWN_LANES:
        until = breaker_state.load(_key(lane))  # None if absent or cooldown elapsed
        if until is None:
            continue
        with _lock:
            _st(lane).opened_at = (until - timedelta(seconds=COOLDOWN_SECONDS)).timestamp()
        logger.info(
            f"[yf-breaker:{lane}] restored OPEN from disk (cooldown until {until.isoformat()})"
        )
        restored = True
    return restored


def record_success(lane: str = LANE_DEFAULT) -> None:
    """Mark a successful yfinance call. Closes `lane` if it was half-open."""
    with _lock:
        st = _st(lane)
        was_open = st.opened_at is not None
        if was_open:
            logger.info(f"[yf-breaker:{lane}] success after open → closing")
        st.failures.clear()
        st.opened_at = None
        st.half_open_in_flight = False
        st.half_open_at = None
    if was_open:
        _persist_clear(lane)  # only touch disk on a real open→closed transition


def record_failure(reason: str = "", lane: str = LANE_DEFAULT) -> None:
    """Mark a yfinance failure on `lane`. May trip that lane's breaker."""
    now = time.time()
    opened_now = False
    with _lock:
        st = _st(lane)
        if st.half_open_in_flight:
            # Half-open probe failed → re-open with a fresh cooldown
            st.half_open_in_flight = False
            st.half_open_at = None
            st.opened_at = now
            opened_now = True
            logger.warning(
                f"[yf-breaker:{lane}] half-open probe failed ({reason}) "
                f"→ re-open for {COOLDOWN_SECONDS}s"
            )
        else:
            _prune_old(st, now)
            st.failures.append(now)
            if st.opened_at is None and len(st.failures) >= N_FAILURES:
                st.opened_at = now
                opened_now = True
                logger.warning(
                    f"[yf-breaker:{lane}] {len(st.failures)} failures in {WINDOW_SECONDS}s "
                    f"({reason}) → OPEN for {COOLDOWN_SECONDS}s"
                )
    if opened_now:
        _persist_open(lane, now, reason)


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


def call_protected(
    name: str, fn: Callable[[], T], default: T | None = None, lane: str = LANE_DEFAULT
) -> T | None:
    """Run `fn()`, recording outcome to `lane`'s breaker. Returns `default` if the
    breaker is open or the call raises a rate-limit-type error.

    Use for yfinance calls where a partial failure should be transparent to
    the caller (e.g. micro data — if breaker is open, return MicroData()).
    """
    if is_open(lane):
        return default
    try:
        out = fn()
    except Exception as exc:  # noqa: BLE001
        if is_rate_limit_error(exc):
            record_failure(f"{name}: {exc}", lane=lane)
            return default
        # Other exceptions don't trip the breaker but still bubble up so the
        # caller can decide.
        raise
    # We don't record success here for individual sub-calls because yfinance
    # can return a structurally valid empty payload even when rate-limited;
    # callers that get a "real" response (e.g. non-empty DataFrame) should
    # call record_success() explicitly.
    return out


def _lane_status(st: _State, now: float) -> dict:
    _prune_old(st, now)
    if st.opened_at is not None:
        seconds_until_probe = max(0.0, COOLDOWN_SECONDS - (now - st.opened_at))
        out = {
            "state": "half_open" if st.half_open_in_flight else "open",
            "opened_at": st.opened_at,
            "seconds_until_probe": round(seconds_until_probe, 1),
            # Absolute epoch (UTC seconds) when the cooldown lifts and a
            # half-open probe is allowed. The UI counts down against this so
            # the figure stays accurate between health polls. In half-open
            # this is already in the past (cooldown elapsed → probing now).
            "blocked_until": st.opened_at + COOLDOWN_SECONDS,
            "failures_in_window": len(st.failures),
        }
        if st.half_open_in_flight and st.half_open_at is not None:
            # When the in-flight probe is treated as abandoned and a fresh
            # probe is granted — the UI shows this as the half-open deadline.
            out["probe_deadline"] = st.half_open_at + HALF_OPEN_PROBE_TIMEOUT
        return out
    return {"state": "closed", "failures_in_window": len(st.failures)}


def status(lane: str | None = None) -> dict:
    """Diagnostic snapshot for logging / health endpoint.

    With `lane` → that lane only. Without → the WORST lane's snapshot (so the
    existing UI keeps showing "something is blocked" with the same keys it
    always read), plus a `lanes` breakdown for per-lane detail.
    """
    with _lock:
        now = time.time()
        if lane is not None:
            return _lane_status(_st(lane), now)
        per_lane = {ln: _lane_status(st, now) for ln, st in _states.items()}
    # Worst-first so the headline reflects any blocked lane; among equals the
    # one with the most recent failures wins.
    rank = {"open": 2, "half_open": 1, "closed": 0}
    worst = max(per_lane.values(), key=lambda d: (rank[d["state"]], d["failures_in_window"]))
    return {**worst, "lanes": per_lane}


def reset() -> None:
    """For tests."""
    with _lock:
        for st in _states.values():
            st.failures.clear()
            st.opened_at = None
            st.half_open_in_flight = False
            st.half_open_at = None
