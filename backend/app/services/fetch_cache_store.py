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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FetchCache
from app.services.stock_fundamentals_service import (
    AnalystAction,
    AnalystPriceTarget,
    AnalystRating,
    AnnualPoint,
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


def write_fundamentals(db: Session, fundamentals: Fundamentals) -> None:
    """UPSERT this stock's Fundamentals into the L2 cache."""
    payload = json.dumps(asdict(fundamentals), default=str)
    _upsert(db, fundamentals.ticker, KIND_FUNDAMENTALS, payload)


def read_fundamentals(
    db: Session, ticker: str, max_age_seconds: int
) -> Fundamentals | None:
    """Return a Fundamentals from L2 iff present AND fresh; None otherwise."""
    row = _read_row(db, ticker, KIND_FUNDAMENTALS, max_age_seconds)
    if row is None:
        return None
    payload_json, fetched_at = row
    try:
        d = json.loads(payload_json)
    except json.JSONDecodeError:
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


# ─── Hydration helpers (used at startup) ────────────────────────────────────

def hydrate_all_fundamentals(
    db: Session, max_age_seconds: int
) -> dict[str, Fundamentals]:
    """Read every fresh fundamentals row from L2 and rebuild a {ticker: F}
    dict suitable for assigning to the in-memory L1 cache.

    Called once during app startup so the first request after a restart
    doesn't have to round-trip the DB per ticker."""
    rows = db.execute(
        select(FetchCache).where(FetchCache.kind == KIND_FUNDAMENTALS)
    ).scalars().all()
    out: dict[str, Fundamentals] = {}
    now = datetime.now(UTC)
    for r in rows:
        fetched = r.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if (now - fetched).total_seconds() > max_age_seconds:
            continue
        try:
            d = json.loads(r.payload)
        except json.JSONDecodeError:
            continue
        f = _fundamentals_from_dict(d)
        f.fetched_at = fetched.timestamp()
        out[r.ticker] = f
    return out


def hydrate_all_news(
    db: Session, max_age_seconds: int
) -> dict[str, tuple[datetime, list[dict[str, Any]]]]:
    """Read every fresh news row from L2 and rebuild the (timestamp, items)
    tuple shape that `stock_news_service._CACHE` uses."""
    rows = db.execute(
        select(FetchCache).where(FetchCache.kind == KIND_NEWS)
    ).scalars().all()
    out: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
    now = datetime.now(UTC)
    for r in rows:
        fetched = r.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if (now - fetched).total_seconds() > max_age_seconds:
            continue
        try:
            items = json.loads(r.payload)
        except json.JSONDecodeError:
            continue
        if isinstance(items, list):
            out[r.ticker] = (fetched, items)
    return out
