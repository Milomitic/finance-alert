"""Persistent (L2) snapshot of the last GOOD live quote per ticker.

WHY THIS EXISTS — and why it reverses an earlier decision
─────────────────────────────────────────────────────────
CLAUDE.md documented that live quotes were deliberately NOT backed by L2:
"its TTL is 10 seconds — a 30s-old quote is worse than re-fetching". That
reasoning was sound while re-fetching was fast. It is not any more: under
Yahoo rate-limiting we measured live-quote requests taking **43-50 seconds**
(incident 2026-07-23, which also starved the health endpoint and got the pod
liveness-killed). A 30-second-old price beats a 50-second wait, and it beats
an empty page after a pod restart. So the premise changed, and with it the
decision.

This layer is a FLOOR, never a source of truth:
- it is only ever consulted when the live path cannot answer NOW (breaker
  open, deadline blown, cold cache after a restart);
- what it returns is flagged stale via `market_state="STALE"` so the UI can
  say so honestly rather than presenting an old price as live;
- it never satisfies a request the live path could have served.

Writes are BATCHED, not per-quote: the intraday sweep marks tickers dirty as
it walks the universe and flushes them in one transaction at the end of its
pass. Per-quote commits would mean ~1000 write transactions every few
minutes for data whose whole purpose is to be a fallback.
"""
import json
from threading import Lock
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FetchCache

KIND = "live_quote"

# Keys persisted per ticker. Deliberately a SUBSET of LiveQuote: the derived
# fields (change_abs/change_pct) are recomputed on read, and `error` is never
# persisted — a cached failure is worse than no cache (same rule the
# fundamentals/news L2 follows).
FIELDS = (
    "price", "prev_close", "day_open", "day_high", "day_low",
    "volume", "currency", "as_of_date", "fetched_at",
)

# SQLite caps host parameters (historically 999). Chunk the IN() lookups so a
# full-universe flush can't trip it on a local dev DB.
_IN_CHUNK = 400

_DIRTY: dict[str, dict[str, Any]] = {}
_LOCK = Lock()


def mark_dirty(ticker: str, payload: dict[str, Any]) -> None:
    """Queue a ticker's snapshot for the next flush(). Cheap, in-memory."""
    with _LOCK:
        _DIRTY[ticker] = payload


def pending() -> int:
    with _LOCK:
        return len(_DIRTY)


def reset() -> None:
    """For tests: drop the queue without writing it."""
    with _LOCK:
        _DIRTY.clear()


def flush(db: Session) -> int:
    """UPSERT every queued snapshot in ONE transaction. Returns rows written."""
    with _LOCK:
        batch = dict(_DIRTY)
        _DIRTY.clear()
    if not batch:
        return 0

    tickers = list(batch)
    existing: dict[str, FetchCache] = {}
    for i in range(0, len(tickers), _IN_CHUNK):
        rows = db.execute(
            select(FetchCache).where(
                FetchCache.kind == KIND,
                FetchCache.ticker.in_(tickers[i : i + _IN_CHUNK]),
            )
        ).scalars().all()
        existing.update({r.ticker: r for r in rows})

    from datetime import UTC, datetime
    now = datetime.now(UTC)
    for ticker, payload in batch.items():
        blob = json.dumps(payload, separators=(",", ":"))
        row = existing.get(ticker)
        if row is None:
            db.add(FetchCache(ticker=ticker, kind=KIND, payload=blob, fetched_at=now))
        else:
            row.payload = blob
            row.fetched_at = now
    db.commit()
    logger.info(f"[live-quote-l2] flushed {len(batch)} snapshots")
    return len(batch)


def load_all(db: Session) -> dict[str, dict[str, Any]]:
    """Every persisted snapshot, for hydrating the in-process store at boot."""
    out: dict[str, dict[str, Any]] = {}
    rows = db.execute(select(FetchCache).where(FetchCache.kind == KIND)).scalars().all()
    for r in rows:
        try:
            out[r.ticker] = json.loads(r.payload)
        except (ValueError, TypeError):
            continue  # a corrupt blob must never block startup
    return out
