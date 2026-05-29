"""L2 cache persistence layer for upstream fetches (fundamentals, news).

The pattern:
- Service `get_X(ticker)` first checks its in-memory L1 dict (microsecond hit).
- L1 miss → call `read_X(db, ticker, max_age_seconds)`. Hits return a hydrated
  object AND populate L1 so subsequent calls in the same process are fast.
- L2 miss / stale → fall through to the upstream network fetch, then call
  `write_X(db, ...)` to UPSERT.

Why a serialization helper module instead of putting it in each service:
- Both services do the same dance (JSON encode → store, fetch → JSON decode →
  reconstruct dataclass). Sharing the orm/json bookkeeping in one place keeps
  each service file focused on its domain logic.
- Fundamentals is a non-trivial nested dataclass tree (annual / quarterly /
  earnings / micro / insiders / analyst_ratings / analyst_actions /
  price_target). The reconstructor lives here so changes to the dataclass
  shape only require an update in one place.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FetchCache
from app.services.stock_fundamentals_service import (
    AnalystAction,
    AnalystPriceTarget,
    AnalystRating,
    AnnualPoint,
    CompanyProfile,
    EarningsPoint,
    Fundamentals,
    InsiderTransaction,
    MicroData,
    QuarterlyPoint,
)

# `kind` discriminator values — kept as constants so a typo can't silently
# create a parallel cache namespace.
KIND_FUNDAMENTALS = "fundamentals"
KIND_NEWS = "news"

# Bumps each time we add a non-trivial field to the Fundamentals dataclass
# tree. Old payloads with a lower version are treated as stale on read so
# the next access re-fetches from yfinance and writes the new shape — even
# if the row is still within the 24h TTL. This avoids:
#   - A bulk wipe that would force every stock to re-fetch at once.
#   - Per-field heuristics ("if profile is empty, refetch") that conflate
#     "missing data" with "old schema".
# Versions:
#   1: pre-CompanyProfile (annual/quarterly/earnings/micro/insiders/...)
#   2: + CompanyProfile (long_business_summary, website, employees, ...)
#   3: + comprehensive MicroData expansion (~25 new yfinance fields:
#        ebitda, total_revenue, gross_profits, total_cash, total_debt,
#        eps_trailing/forward/current_year, shares_outstanding/float/short,
#        recommendation_mean, governance risks, etc.). Old payloads
#        re-fetch on next access so users see the richer dataset.
# v6 — insiders extraction now drops transactions <500 shares post-coalesce
#       (noise floor for stock gifts / director admin transfers). Old payloads
#       cached with no filter must be re-fetched so the UI doesn't keep
#       surfacing the stale unfiltered list.
# v7 — MicroData gained revenue_quarterly_growth (Rev QoQ), earnings_growth_5y
#       and revenue_growth_5y (history-derived 5Y CAGRs), plus the growth
#       reconciliation (yfinance YoY/QoQ vs reported-EPS series) and the
#       Finnhub revenue est/actual backfill. Pre-deploy payloads carry these
#       as null and would otherwise never re-fetch (same schema + fresh TTL),
#       so they MUST be invalidated to populate the new fundamentals.
_FUNDAMENTALS_SCHEMA_VERSION = 7
_SCHEMA_VERSION_KEY = "_schema_version"


# ─── Generic UPSERT helper ──────────────────────────────────────────────────
def _upsert(db: Session, ticker: str, kind: str, payload: str) -> None:
    """SQLAlchemy `merge`-equivalent without needing the model's PK injection.
    Reads the row by composite key and updates in place if present."""
    existing = db.execute(
        select(FetchCache).where(
            FetchCache.ticker == ticker, FetchCache.kind == kind
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is None:
        db.add(FetchCache(ticker=ticker, kind=kind, payload=payload, fetched_at=now))
    else:
        existing.payload = payload
        existing.fetched_at = now
    db.commit()


def _read_row(
    db: Session, ticker: str, kind: str, max_age_seconds: int
) -> tuple[str, datetime] | None:
    """Return (payload_json, fetched_at) iff the row exists AND is fresh."""
    row = db.execute(
        select(FetchCache).where(
            FetchCache.ticker == ticker, FetchCache.kind == kind
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    # SQLite returns naive datetimes — coerce to UTC for the diff to work.
    fetched = row.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - fetched).total_seconds()
    if age > max_age_seconds:
        return None
    return row.payload, fetched


# ─── Fundamentals (de)serialization ─────────────────────────────────────────
# Fundamentals is a tree of nested dataclasses. asdict() flattens to dicts of
# primitives + lists; we reconstruct by walking the tree with a manifest of
# field-name → dataclass-type for the nested bits.
_FUND_NESTED_FIELDS: dict[str, type] = {
    "micro": MicroData,
    "profile": CompanyProfile,
    "price_target": AnalystPriceTarget,
}
_FUND_LIST_FIELDS: dict[str, type] = {
    "annual": AnnualPoint,
    "quarterly": QuarterlyPoint,
    "earnings": EarningsPoint,
    "insiders": InsiderTransaction,
    "analyst_ratings": AnalystRating,
    "analyst_actions": AnalystAction,
}


def _dataclass_from_dict(cls: type, d: dict[str, Any]) -> Any:
    """Reconstruct a flat dataclass instance, defaulting any missing fields.

    Used for the leaf dataclasses (no nested dataclasses inside them — those
    don't exist in our shape). For the top-level Fundamentals, see
    `fundamentals_from_dict` which handles the nested structure explicitly.
    """
    if not is_dataclass(cls):
        raise TypeError(f"_dataclass_from_dict expects a dataclass, got {cls}")
    valid_keys = {f.name for f in fields(cls)}
    # Filter out unknown keys defensively — old payloads in L2 might have
    # been written by an older service version with extra fields, and a new
    # version without them shouldn't crash on load.
    return cls(**{k: v for k, v in d.items() if k in valid_keys})


def _fundamentals_from_dict(d: dict[str, Any]) -> Fundamentals:
    """Walk the dict + reconstruct nested dataclasses into a Fundamentals tree."""
    # Copy so we don't mutate the caller's dict.
    payload = dict(d)
    for key, leaf_type in _FUND_NESTED_FIELDS.items():
        sub = payload.get(key)
        if isinstance(sub, dict):
            payload[key] = _dataclass_from_dict(leaf_type, sub)
    for key, leaf_type in _FUND_LIST_FIELDS.items():
        sub = payload.get(key)
        if isinstance(sub, list):
            payload[key] = [
                _dataclass_from_dict(leaf_type, x) if isinstance(x, dict) else x
                for x in sub
            ]
    # Filter unknown top-level keys for forward-compat.
    valid_keys = {f.name for f in fields(Fundamentals)}
    return Fundamentals(**{k: v for k, v in payload.items() if k in valid_keys})


def _is_payload_stale_schema(d: dict[str, Any]) -> bool:
    """True if the parsed payload predates the current schema version.
    Missing key → version 1 (the original shape, no `_schema_version`)."""
    return int(d.get(_SCHEMA_VERSION_KEY, 1)) < _FUNDAMENTALS_SCHEMA_VERSION


def _is_payload_too_partial(d: dict[str, Any]) -> bool:
    """True iff the parsed fundamentals payload is missing the data that
    comes from the slow `Ticker.info` call — micro is all None AND
    profile has no business-summary or website.

    Why force a re-fetch on these: yfinance occasionally rate-limits or
    fails the slow info call mid-batch while OTHER endpoints in the
    fetch (income_stmt, quarterly_income_stmt, etc.) succeed. The result
    is a payload that looks like a successful fetch (no top-level
    exception, error=None) but is missing the most user-visible bits —
    company profile text, P/E, ROE, margins, market cap, etc. That
    payload then sits in L2 for the full 24h TTL with no error
    indication, and the user sees an empty 'Profilo Società' card and
    empty 'Valutazione' card every time.

    Treating these as stale on read forces a re-fetch on next access.
    Combined with the symmetric write-side check in
    `stock_fundamentals_service._fetch_fresh`, this prevents new
    partials from entering L2 going forward.

    Negative-cache exception: if `error` is set, this is an INTENTIONAL
    "ticker has no data" entry written by the negative-cache path —
    return False so the L2 read serves it instead of forcing yet another
    expensive re-fetch. The shorter `_NEGATIVE_TTL_SECONDS` in
    stock_fundamentals_service caps how long we trust the negative
    record (6h vs the standard 24h) — long enough to spare per-restart
    cost, short enough that a re-listed ticker recovers."""
    if d.get("error"):
        return False
    micro = d.get("micro") if isinstance(d.get("micro"), dict) else {}
    profile = d.get("profile") if isinstance(d.get("profile"), dict) else {}
    has_micro = any(v is not None for v in (micro or {}).values())
    has_profile = bool(
        (profile or {}).get("long_business_summary")
        or (profile or {}).get("website")
    )
    return not (has_micro or has_profile)


def write_fundamentals(db: Session, fundamentals: Fundamentals) -> None:
    """UPSERT this stock's Fundamentals into the L2 cache."""
    obj = asdict(fundamentals)
    obj[_SCHEMA_VERSION_KEY] = _FUNDAMENTALS_SCHEMA_VERSION
    payload = json.dumps(obj, default=str)
    _upsert(db, fundamentals.ticker, KIND_FUNDAMENTALS, payload)


def read_fundamentals(
    db: Session, ticker: str, max_age_seconds: int
) -> Fundamentals | None:
    """Return a Fundamentals from L2 iff present AND fresh; None otherwise.

    Returns None for ANY of: missing row, expired row, schema-version
    mismatch, or unparseable JSON. Schema-version mismatch is the trigger
    for a graceful migration to a newer shape (e.g. when CompanyProfile
    was added, all old rows naturally re-fetch as users access them).
    """
    row = _read_row(db, ticker, KIND_FUNDAMENTALS, max_age_seconds)
    if row is None:
        return None
    payload_json, fetched_at = row
    try:
        d = json.loads(payload_json)
    except json.JSONDecodeError:
        return None
    if _is_payload_stale_schema(d):
        return None
    if _is_payload_too_partial(d):
        # Treat as stale: forces an upstream re-fetch on next access.
        # See _is_payload_too_partial for the rationale.
        return None
    f = _fundamentals_from_dict(d)
    # Reset `fetched_at` to the L2 timestamp (epoch seconds) so the L1
    # cache layer's TTL check stays consistent — it uses the same field.
    f.fetched_at = fetched_at.timestamp()
    return f


# ─── News (de)serialization ─────────────────────────────────────────────────
# News is just `list[dict]` — no dataclass reconstruction needed.

def write_news(db: Session, ticker: str, items: list[dict[str, Any]]) -> None:
    payload = json.dumps(items, default=str)
    _upsert(db, ticker, KIND_NEWS, payload)


def read_news(
    db: Session, ticker: str, max_age_seconds: int
) -> list[dict[str, Any]] | None:
    row = _read_row(db, ticker, KIND_NEWS, max_age_seconds)
    if row is None:
        return None
    try:
        items = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return items if isinstance(items, list) else None


def read_fetched_at(db: Session, ticker: str, kind: str) -> float | None:
    """Epoch-seconds timestamp of the L2 row for (ticker, kind), regardless of
    freshness (TTL is NOT enforced — callers want to DISPLAY the data's age, not
    gate on it). None when no row exists. Used to surface true data age in the
    UI's "aggiornato …" label so it survives page reloads."""
    fetched = db.execute(
        select(FetchCache.fetched_at)
        .where(FetchCache.ticker == ticker, FetchCache.kind == kind)
        .limit(1)
    ).scalars().first()
    if fetched is None:
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return fetched.timestamp()


# ─── Hydration helpers (used at startup) ────────────────────────────────────

def hydrate_all_fundamentals(
    db: Session, max_age_seconds: int
) -> tuple[dict[str, Fundamentals], int]:
    """Read every fresh fundamentals row from L2 and rebuild a {ticker: F}
    dict suitable for assigning to the in-memory L1 cache.

    Called once during app startup so the first request after a restart
    doesn't have to round-trip the DB per ticker. Skips rows that fail
    schema validation (old version) — those will re-fetch on first
    access via `get_fundamentals`.

    Returns:
        (entries, skipped) — entries is the loaded dict; skipped is the count
        of rows that failed deserialization or schema validation."""
    rows = db.execute(
        select(FetchCache).where(FetchCache.kind == KIND_FUNDAMENTALS)
    ).scalars().all()
    out: dict[str, Fundamentals] = {}
    skipped = 0
    now = datetime.now(UTC)
    for r in rows:
        fetched = r.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if (now - fetched).total_seconds() > max_age_seconds:
            continue
        try:
            d = json.loads(r.payload)
            if _is_payload_stale_schema(d):
                skipped += 1
                continue
            if _is_payload_too_partial(d):
                # Skip; the next `get_fundamentals` for this ticker will
                # see L1 miss + L2 read-skip and re-fetch upstream.
                skipped += 1
                continue
            f = _fundamentals_from_dict(d)
            f.fetched_at = fetched.timestamp()
            out[r.ticker] = f
        except Exception as exc:  # noqa: BLE001 — corrupt row, skip + log
            logger.warning(
                f"[fetch_cache_store] hydrate skip fundamentals {r.ticker!r}: {exc!r}"
            )
            skipped += 1
    return out, skipped


def hydrate_all_news(
    db: Session, max_age_seconds: int
) -> tuple[dict[str, tuple[datetime, list[dict[str, Any]]]], int]:
    """Read every fresh news row from L2 and rebuild the (timestamp, items)
    tuple shape that `stock_news_service._CACHE` uses.

    Returns:
        (entries, skipped) — entries is the loaded dict; skipped is the count
        of rows that failed deserialization."""
    rows = db.execute(
        select(FetchCache).where(FetchCache.kind == KIND_NEWS)
    ).scalars().all()
    out: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
    skipped = 0
    now = datetime.now(UTC)
    for r in rows:
        fetched = r.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if (now - fetched).total_seconds() > max_age_seconds:
            continue
        try:
            items = json.loads(r.payload)
            if isinstance(items, list):
                out[r.ticker] = (fetched, items)
            else:
                logger.warning(
                    f"[fetch_cache_store] hydrate skip news {r.ticker!r}: "
                    f"payload is {type(items).__name__}, expected list"
                )
                skipped += 1
        except Exception as exc:  # noqa: BLE001 — corrupt row, skip + log
            logger.warning(
                f"[fetch_cache_store] hydrate skip news {r.ticker!r}: {exc!r}"
            )
            skipped += 1
    return out, skipped
