"""Per-source / per-operation counters for the data-fetching layer.

Tracks how often each backend service successfully retrieves data vs how
often it fails, so the operator can see at-a-glance whether a given source
is reliable or whether more fallbacks need wiring.

Stored in-process (single uvicorn worker) — fine for a local-first tool.
A reset() helper makes it test-friendly. Counters are timestamped per
operation so we also know "last success at" for staleness reasoning.

Each counter also keeps a small ring buffer of recent call timestamps
(bounded; ~25KB total across all sources) so we can answer "how many
calls in the last N seconds" — used for rate-limit usage indicators in
the platform-health UI (Finnhub free tier 60/min, Marketaux 100/day…).

Sources currently tracked:
- yfinance.ohlcv      — yfinance.download() batch path (no fallback in 2026: Stooq
                        introduced apikey gate, Finnhub /stock/candle is paywalled,
                        Polygon free is 5/min — no viable batch alternative)
- yfinance.market_cap — yfinance.Ticker.fast_info marketCap
- yfinance.fundamentals — yfinance.Ticker.* (income_stmt, info, etc.)
- yfinance.live_quote — yfinance.Ticker.fast_info per-tab polling
- yfinance.news       — yfinance.Ticker.news headlines
- finnhub.earnings    — Finnhub fallback for actual earnings
- fred.macro          — FRED macro series download
- marketaux.news      — Marketaux fallback when yfinance returns empty
- forexfactory.consensus — ForexFactory macro consensus
- sec_13f.filings     — SEC EDGAR 13F filings scraper
"""
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

# How many recent call timestamps to keep per (source, op). 200 covers a
# Marketaux daily window (100/day with margin) and ~3min of Finnhub-pace
# traffic (60/min). Bounded so memory stays trivial even with many sources.
_RECENT_MAX = 200


@dataclass
class _Counter:
    success: int = 0
    failure: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_failure_reason: str | None = None
    # Timestamps of recent calls (success or failure). Bounded ring buffer.
    recent_calls: deque = field(default_factory=lambda: deque(maxlen=_RECENT_MAX))


_counters: dict[str, _Counter] = {}
_lock = Lock()


def _key(source: str, op: str) -> str:
    return f"{source}.{op}"


def record_success(source: str, op: str, count: int = 1) -> None:
    """Record `count` successful fetch operations on (source, op)."""
    now = time.time()
    with _lock:
        c = _counters.setdefault(_key(source, op), _Counter())
        c.success += count
        c.last_success_at = now
        # Record one timestamp per call (bounded ring buffer); used by
        # calls_in_window() for rate-limit usage indicators.
        for _ in range(count):
            c.recent_calls.append(now)


def record_failure(source: str, op: str, reason: str = "", count: int = 1) -> None:
    """Record `count` failed fetch operations. `reason` is captured for the
    most recent failure only (the user just needs the latest hint)."""
    now = time.time()
    with _lock:
        c = _counters.setdefault(_key(source, op), _Counter())
        c.failure += count
        c.last_failure_at = now
        if reason:
            # Trim long messages — we only want a hint
            c.last_failure_reason = reason[:200]
        for _ in range(count):
            c.recent_calls.append(now)


def seconds_since_last_success(source: str, op: str) -> float | None:
    """Wall-clock seconds since the last successful call on (source, op).

    Returns None when the source has never recorded a success (so the
    caller can distinguish "never tested" from "tested long ago").

    Used by health probes that want to elide their own call when organic
    traffic recently confirmed the source — e.g. Marketaux probe skips
    the round-trip if a real fetch succeeded in the last 4h, sparing
    one of the 100/day free-tier units."""
    with _lock:
        c = _counters.get(_key(source, op))
        if c is None or c.last_success_at is None:
            return None
        return time.time() - c.last_success_at


def calls_in_window(source: str, op: str, window_seconds: float) -> int:
    """Count calls (success+failure) on (source, op) in the last `window_seconds`.

    Bounded by `_RECENT_MAX` — older calls are evicted from the ring buffer
    so for windows larger than ~3min on a busy source the count saturates
    at _RECENT_MAX. That's intentional: rate-limit indicators don't need
    exact long-window precision, just "approaching the limit / not".
    """
    cutoff = time.time() - window_seconds
    with _lock:
        c = _counters.get(_key(source, op))
        if c is None:
            return 0
        return sum(1 for t in c.recent_calls if t >= cutoff)


@dataclass
class SourceMetric:
    source: str
    op: str
    success: int
    failure: int
    success_rate: float            # 0.0..1.0; -1 if no calls yet
    last_success_at: float | None
    last_failure_at: float | None
    last_failure_reason: str | None
    health: str                    # "healthy" | "degraded" | "failing" | "idle"


def _classify(c: _Counter) -> tuple[float, str]:
    total = c.success + c.failure
    if total == 0:
        return -1.0, "idle"
    rate = c.success / total
    # Recent-failure window: if the last failure is in the last 60s and there's
    # no success after it, downgrade health regardless of historical rate.
    now = time.time()
    recent_fail = c.last_failure_at is not None and (now - c.last_failure_at) < 60
    last_op_was_failure = (
        c.last_failure_at is not None and (
            c.last_success_at is None or c.last_failure_at > c.last_success_at
        )
    )
    if recent_fail and last_op_was_failure:
        return rate, "failing"
    if rate >= 0.85:
        return rate, "healthy"
    if rate >= 0.5:
        return rate, "degraded"
    return rate, "failing"


def snapshot() -> list[SourceMetric]:
    """Return a current snapshot of all counters, sorted by source then op."""
    with _lock:
        rows: list[SourceMetric] = []
        for key, c in sorted(_counters.items()):
            source, _, op = key.partition(".")
            rate, health = _classify(c)
            rows.append(SourceMetric(
                source=source, op=op,
                success=c.success, failure=c.failure,
                success_rate=round(rate, 3) if rate >= 0 else -1.0,
                last_success_at=c.last_success_at,
                last_failure_at=c.last_failure_at,
                last_failure_reason=c.last_failure_reason,
                health=health,
            ))
        return rows


@dataclass
class GapAnalysis:
    """Suggestion the operator should consider when a source is unhealthy."""
    op: str
    why: str
    suggestion: str


def analyse_gaps() -> list[GapAnalysis]:
    """Heuristic: for each operation where the only source is failing or
    degraded, suggest adding a fallback. For operations that already have
    a working fallback, stay quiet."""
    suggestions: list[GapAnalysis] = []
    snap = snapshot()
    by_op: dict[str, list[SourceMetric]] = {}
    for s in snap:
        by_op.setdefault(s.op, []).append(s)

    fallback_hints = {
        "market_cap": "Aggiungere fallback es. FinancialModelingPrep free-tier per market cap.",
        "fundamentals": "Aggiungere fallback es. SEC EDGAR (revenue+EPS, US-only) o FinancialModelingPrep free-tier.",
        "ohlcv": "Nessun fallback OHLCV gratuito viable in 2026 (Stooq apikey-gated, Finnhub /candle paywalled, Polygon free 5/min, Tiingo 1000/day). Quando yfinance breaker apre, lo scan skippa e ritenta al ciclo successivo.",
    }

    for op, sources in by_op.items():
        # If ANY source is healthy, no suggestion.
        if any(s.health == "healthy" for s in sources):
            continue
        # All sources failing/degraded for this op → suggest fallback
        bad = [s for s in sources if s.health in ("failing", "degraded")]
        if not bad:
            continue
        sources_str = ", ".join(f"{s.source}({s.health})" for s in bad)
        suggestions.append(GapAnalysis(
            op=op,
            why=f"Sources {sources_str} non riescono a fornire dati affidabili.",
            suggestion=fallback_hints.get(op, "Considera l'aggiunta di una fonte alternativa per questa operazione."),
        ))
    return suggestions


def reset() -> None:
    """Clear all counters — for tests."""
    with _lock:
        _counters.clear()
