"""Tests for the market_snapshot parse memo (B4-11a).

The ~264 KB payload blob used to be json.loads-ed on EVERY request by three
consumers (market-summary endpoint, spotlight cards, pre-market pool). Now
`market_stats_service.get_latest_snapshot_payload` parses once per snapshot,
keyed on (row id, computed_at): same snapshot → memo hit; a recompute (new
computed_at) → natural invalidation. Conftest clears `_PAYLOAD_MEMO` between
tests (each test has its own in-memory DB, ids/timestamps could collide).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import MarketSnapshot
from app.services import market_stats_service as mss


def _seed_snapshot(
    db: Session, payload: object, *, computed_at: datetime,
) -> MarketSnapshot:
    """Create/overwrite the single live snapshot row (id=1)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    snap = db.get(MarketSnapshot, 1)
    if snap is None:
        snap = MarketSnapshot(
            id=1, computed_at=computed_at, stocks_total=10,
            stocks_with_data=10, payload=raw,
        )
        db.add(snap)
    else:
        snap.computed_at = computed_at
        snap.payload = raw
    db.commit()
    return snap


@pytest.fixture
def _parse_spy(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Counts calls into the real `_parse_payload` (the memoized work unit)."""
    calls = {"n": 0}
    orig = mss._parse_payload

    def spy(raw):
        calls["n"] += 1
        return orig(raw)

    monkeypatch.setattr(mss, "_parse_payload", spy)
    return calls


def test_parse_happens_once_per_snapshot(db: Session, _parse_spy: dict):
    _seed_snapshot(
        db, {"movers": {"gainers": [{"ticker": "AAA"}]}},
        computed_at=datetime(2026, 7, 1, 23, 30, tzinfo=UTC),
    )
    snap1, p1 = mss.get_latest_snapshot_payload(db)
    snap2, p2 = mss.get_latest_snapshot_payload(db)
    assert snap1 is not None and snap2 is not None
    assert _parse_spy["n"] == 1          # second call is a memo hit
    assert p1 is p2                      # the SAME shared dict, not a re-parse
    assert p1["movers"]["gainers"][0]["ticker"] == "AAA"


def test_new_snapshot_invalidates_memo(db: Session, _parse_spy: dict):
    _seed_snapshot(
        db, {"v": 1}, computed_at=datetime(2026, 7, 1, 23, 30, tzinfo=UTC),
    )
    _, p1 = mss.get_latest_snapshot_payload(db)
    assert p1 == {"v": 1}

    # recompute_snapshot writes a fresh computed_at → key changes → re-parse.
    _seed_snapshot(
        db, {"v": 2}, computed_at=datetime(2026, 7, 2, 23, 30, tzinfo=UTC),
    )
    _, p2 = mss.get_latest_snapshot_payload(db)
    assert p2 == {"v": 2}
    assert _parse_spy["n"] == 2


def test_no_snapshot_returns_none_and_empty(db: Session):
    snap, payload = mss.get_latest_snapshot_payload(db)
    assert snap is None
    assert payload == {}


def test_corrupt_payload_degrades_to_empty_dict(db: Session):
    _seed_snapshot(
        db, "{ not json", computed_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    snap, payload = mss.get_latest_snapshot_payload(db)
    assert snap is not None
    assert payload == {}


def test_non_dict_payload_degrades_to_empty_dict(db: Session):
    _seed_snapshot(
        db, [1, 2, 3], computed_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    _, payload = mss.get_latest_snapshot_payload(db)
    assert payload == {}
