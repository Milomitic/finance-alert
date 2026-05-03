"""Per-source / per-operation counters for the data-fetching layer.

Tracks how often each backend service successfully retrieves data vs how
often it fails, so the operator can see at-a-glance whether a given source
is reliable or whether more fallbacks need wiring.

Stored in-process (single uvicorn worker) — fine for a local-first tool.
A reset() helper makes it test-friendly. Counters are timestamped per
operation so we also know "last success at" for staleness reasoning.

Sources currently tracked:
- yfinance.ohlcv      — yfinance.download() batch path
- yfinance.market_cap — yfinance.Ticker.fast_info marketCap
- yfinance.fundamentals — yfinance.Ticker.* (income_stmt, info, etc.)
- stooq.ohlcv         — Stooq CSV fallback for OHLCV
"""
import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _Counter:
    success: int = 0
    failure: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_failure_reason: str | None = None


_counters: dict[str, _Counter] = {}
_lock = Lock()


def _key(source: str, op: str) -> str:
    return f"{source}.{op}"


def record_success(source: str, op: str, count: int = 1) -> None:
    """Record `count` successful fetch operations on (source, op)."""
    with _lock:
        c = _counters.setdefault(_key(source, op), _Counter())
        c.success += count
        c.last_success_at = time.time()


def record_failure(source: str, op: str, reason: str = "", count: int = 1) -> None:
    """Record `count` failed fetch operations. `reason` is captured for the
    most recent failure only (the user just needs the latest hint)."""
    with _lock:
        c = _counters.setdefault(_key(source, op), _Counter())
        c.failure += count
        c.last_failure_at = time.time()
        if reason:
            # Trim long messages — we only want a hint
            c.last_failure_reason = reason[:200]


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
        "market_cap": "Aggiungere fallback es. Stooq Insider list / FinancialModelingPrep free-tier per market cap.",
        "fundamentals": "Aggiungere fallback es. SEC EDGAR (revenue+EPS, US-only) o FinancialModelingPrep free-tier.",
        "ohlcv": "Stooq è già il fallback OHLCV. Se anche Stooq degrada, valutare yahoo-fin (alt parser) o Alpha Vantage (free 5 req/min, key richiesta).",
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
