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
- dataroma.holdings   — Dataroma superinvestor portfolios scraper
"""
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

from app.core import persist_json

# Failure reasons carrying an HTTP 403 mark the call as PLAN-GATED (the
# upstream understood us fine and said "your tier doesn't include this"):
# finnhub upgrade-downgrade on the free tier, twelvedata outside the plan…
# Those sources are classified "unavailable" (slate in the UI, excluded from
# the degraded-banner rollup) instead of pinning the banner amber forever.
# \b boundaries so "1403ms" or "HTTP 4033" never match.
_HTTP_403_RE = re.compile(r"\b403\b")

# How many recent call timestamps to keep per (source, op). 200 covers a
# Marketaux daily window (100/day with margin) and ~3min of Finnhub-pace
# traffic (60/min). Bounded so memory stays trivial even with many sources.
_RECENT_MAX = 200


@dataclass
class _Counter:
    success: int = 0
    failure: int = 0
    # How many of the failures were HTTP 403 (plan-gated). When ALL failures
    # are 403 the classifier reads the source as "unavailable" — a tier/plan
    # limitation, not an outage.
    failure_403: int = 0
    # Outcome of the LAST batch/call on this (source, op): "ok" | "partial" |
    # "failed". The health classifier keys on THIS (outcome-of-last-batch
    # semantics) instead of a time-decayed failure window vs a non-decaying
    # lifetime rate — the old mix made health flip-flop 60s after a failure
    # while the rate stayed frozen. Single-call sites set ok/failed via
    # record_success/record_failure; batch sites (ohlcv, market_cap) report
    # the whole batch at once via record_batch so a partial batch reads
    # "partial", not whichever of success/failure happened to be recorded last.
    last_batch: str | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_failure_reason: str | None = None
    # Timestamps of recent calls (success or failure). Bounded ring buffer.
    recent_calls: deque = field(default_factory=lambda: deque(maxlen=_RECENT_MAX))


_counters: dict[str, _Counter] = {}
_lock = Lock()

# Persist health counters across restarts so the Salute page (outage status,
# last-error hints, last-success ages) survives a kill+restart instead of
# resetting to Idle. Throttled write-through; the `recent_calls` rate-limit ring
# is intentionally NOT persisted (short rolling window — fine to start empty).
_STATE_FILE = persist_json.data_path("source_metrics.json")
_FLUSH_INTERVAL = 5.0  # seconds — at most one disk write per this interval
_last_flush = 0.0


def _key(source: str, op: str) -> str:
    return f"{source}.{op}"


def _serialize_locked() -> dict[str, dict]:
    """Snapshot the persistable counter fields. Caller holds `_lock`."""
    return {
        key: {
            "success": c.success,
            "failure": c.failure,
            "failure_403": c.failure_403,
            "last_batch": c.last_batch,
            "last_success_at": c.last_success_at,
            "last_failure_at": c.last_failure_at,
            "last_failure_reason": c.last_failure_reason,
        }
        for key, c in _counters.items()
    }


def hydrate_from_dict(data: dict) -> int:
    """Load counters from a serialized dict (pure; no IO). Returns count loaded."""
    with _lock:
        for key, d in data.items():
            if not isinstance(d, dict):
                continue
            c = _counters.setdefault(key, _Counter())
            c.success = int(d.get("success") or 0)
            c.failure = int(d.get("failure") or 0)
            c.last_success_at = d.get("last_success_at")
            c.last_failure_at = d.get("last_failure_at")
            c.last_failure_reason = d.get("last_failure_reason")
            # Legacy state files predate last_batch → leave None; the
            # classifier derives an approximation from the event timestamps.
            if d.get("last_batch") in ("ok", "partial", "failed"):
                c.last_batch = d["last_batch"]
            if "failure_403" in d:
                c.failure_403 = int(d.get("failure_403") or 0)
            elif c.failure > 0 and _HTTP_403_RE.search(c.last_failure_reason or ""):
                # Legacy state file (pre failure_403): the historical counts
                # weren't tagged, so an all-403 source (the plan-gated
                # pattern this exists for) would never flip to
                # "unavailable". If the LAST failure was a 403, assume the
                # history was homogeneous — the assumption self-corrects on
                # the first non-403 failure recorded from now on.
                c.failure_403 = c.failure
        return len(_counters)


def load_from_disk() -> int:
    """Rehydrate counters from the on-disk state file at boot. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return 0
    data = persist_json.read_json(_STATE_FILE)
    if not data:
        return 0
    return hydrate_from_dict(data)


def _persist_if_due() -> None:
    """Throttled write-through of the counters. No-op under pytest."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    global _last_flush
    now = time.time()
    with _lock:
        if now - _last_flush < _FLUSH_INTERVAL:
            return
        _last_flush = now
        data = _serialize_locked()
    persist_json.write_json(_STATE_FILE, data)


def record_success(source: str, op: str, count: int = 1) -> None:
    """Record `count` successful fetch operations on (source, op).

    For single-call sites this IS the batch: the last-batch verdict flips
    to "ok". Batched call sites with mixed outcomes must use record_batch
    instead, or the verdict would reflect only whichever half was recorded
    last."""
    now = time.time()
    with _lock:
        c = _counters.setdefault(_key(source, op), _Counter())
        c.success += count
        c.last_success_at = now
        c.last_batch = "ok"
        # Record one timestamp per call (bounded ring buffer); used by
        # calls_in_window() for rate-limit usage indicators.
        for _ in range(count):
            c.recent_calls.append(now)
    _persist_if_due()


def record_failure(source: str, op: str, reason: str = "", count: int = 1) -> None:
    """Record `count` failed fetch operations. `reason` is captured for the
    most recent failure only (the user just needs the latest hint). The
    last-batch verdict flips to "failed" (see record_success)."""
    now = time.time()
    with _lock:
        c = _counters.setdefault(_key(source, op), _Counter())
        c.failure += count
        if _HTTP_403_RE.search(reason or ""):
            c.failure_403 += count
        c.last_failure_at = now
        c.last_batch = "failed"
        if reason:
            # Trim long messages — we only want a hint
            c.last_failure_reason = reason[:200]
        for _ in range(count):
            c.recent_calls.append(now)
    _persist_if_due()


def record_batch(
    source: str, op: str, *, succeeded: int, failed: int, reason: str = ""
) -> None:
    """Record one BATCH outcome atomically (ohlcv/market_cap style call sites
    that process N tickers per run). Updates the same per-ticker counters as
    record_success/record_failure, but stamps a single per-batch verdict:

        succeeded>0, failed==0  → "ok"       (classifier: healthy)
        succeeded>0, failed>0   → "partial"  (classifier: degraded)
        succeeded==0, failed>0  → "failed"   (classifier: failing)
        both zero               → no-op (nothing happened)

    Without this, a partial batch recorded as success-then-failure would
    read "failed" (or "ok" in the reverse order) — the exact ambiguity the
    outcome-of-last-batch classifier needs resolved at the call site."""
    if succeeded <= 0 and failed <= 0:
        return
    now = time.time()
    with _lock:
        c = _counters.setdefault(_key(source, op), _Counter())
        if succeeded > 0:
            c.success += succeeded
            c.last_success_at = now
        if failed > 0:
            c.failure += failed
            if _HTTP_403_RE.search(reason or ""):
                c.failure_403 += failed
            c.last_failure_at = now
            if reason:
                c.last_failure_reason = reason[:200]
        if failed <= 0:
            c.last_batch = "ok"
        elif succeeded <= 0:
            c.last_batch = "failed"
        else:
            c.last_batch = "partial"
        for _ in range(succeeded + failed):
            c.recent_calls.append(now)
    _persist_if_due()


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
    # "healthy" | "degraded" | "failing" | "unavailable" | "idle"
    health: str


def _classify(c: _Counter) -> tuple[float, str]:
    """Outcome-of-last-batch health. The lifetime success_rate is kept as an
    INFORMATIONAL figure only (rendered in the UI), never as the classifier
    input: a non-decaying lifetime average mixed with a 60s failure window
    made health flip-flop — 'failing' for a minute after any failure, then
    back to whatever the frozen historical rate said."""
    total = c.success + c.failure
    if total == 0:
        return -1.0, "idle"
    rate = c.success / total
    verdict = c.last_batch
    if verdict is None:
        # Legacy persisted state (pre last_batch): approximate the verdict
        # from event ordering — if the most recent event was a failure the
        # last batch failed. Self-corrects on the first new record_* call.
        last_op_was_failure = (
            c.last_failure_at is not None and (
                c.last_success_at is None or c.last_failure_at > c.last_success_at
            )
        )
        verdict = "failed" if last_op_was_failure else "ok"
    if verdict == "failed":
        health = "failing"
    elif verdict == "partial":
        health = "degraded"
    else:
        health = "healthy"
    # Plan-gated override: when EVERY failure was an HTTP 403 the upstream is
    # up but our tier doesn't include the endpoint (finnhub upgrades on the
    # free plan, twelvedata out of plan). Reclassify a would-be
    # failing/degraded as "unavailable" so it doesn't pin the Salute banner
    # amber forever — it's a configuration fact, not an incident. A single
    # non-403 failure (timeout, 5xx, 429) breaks the pattern and the normal
    # classification returns.
    if health in ("failing", "degraded") and c.failure > 0 and c.failure_403 == c.failure:
        health = "unavailable"
    return rate, health


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
