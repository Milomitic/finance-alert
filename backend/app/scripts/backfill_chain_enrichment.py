"""One-off: backfill co-temporal chain enrichment onto EXISTING active signal
alerts (display-only).

Phase 1 enriches chains at scan time, but already-emitted alerts keep their
pre-enrichment 2-step chain until they are re-emitted (and an alert below the
current emission gate may never be). This script re-runs ``enrich_chain``
around each active alert's ORIGINAL ``signal_date`` using stored OHLCV and
updates ``snapshot.chain`` + ``factors.confirmation_count`` IN PLACE. It does
NOT touch ``strength`` / ``probability`` / ``signal_date`` — the original
emission is preserved; only the displayed Catena gains its confirmation steps.

Idempotent: prior ``kind="confirmation"`` steps are stripped before re-enriching.
``gather_events`` is cache-only (no upstream fetch).

Run with uvicorn STOPPED (sole SQLite writer):
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_chain_enrichment
"""
from __future__ import annotations

import json

from sqlalchemy import select

import app.core.db as dbm
from app.models import Alert, Stock
from app.services.scan_service import _load_ohlcv
from app.signals.chain_enrichment import ENRICHABLE, enrich_chain
from app.signals.detectors.base import SignalMatch
from app.signals.events_fundamental import gather_events


def main() -> None:
    scanned = 0
    updated = 0
    with dbm.SessionLocal() as db:
        alerts = db.execute(
            select(Alert).where(
                Alert.archived_at.is_(None),
                Alert.signal_name.in_(tuple(ENRICHABLE)),
            )
        ).scalars().all()

        cache: dict[int, tuple] = {}  # stock_id -> (ohlcv, events, stock)
        for a in alerts:
            scanned += 1
            try:
                snap = json.loads(a.snapshot) if a.snapshot else None
            except (ValueError, TypeError):
                continue
            if not snap or not isinstance(snap.get("chain"), list):
                continue

            # Strip prior confirmations for deterministic, idempotent re-enrich.
            cause = [s for s in snap["chain"] if s.get("kind") != "confirmation"]

            if a.stock_id not in cache:
                stock = db.get(Stock, a.stock_id)
                ohlcv = _load_ohlcv(db, a.stock_id) if stock is not None else None
                events = (
                    gather_events(ohlcv, db=db, stock=stock)
                    if ohlcv is not None and len(ohlcv) else []
                )
                cache[a.stock_id] = (ohlcv, events, stock)
            ohlcv, events, _stock = cache[a.stock_id]
            if ohlcv is None or not len(ohlcv):
                continue

            sig_date = (
                a.signal_date.isoformat() if a.signal_date
                else (cause[-1]["date"] if cause else None)
            )
            if not sig_date:
                continue

            match = SignalMatch(
                name=a.signal_name,
                tone=snap.get("tone", "bull"),
                signal_date=sig_date,
                chain=cause,
                invalidation=snap.get("invalidation"),
                factors={k: v for k, v in (snap.get("factors") or {}).items()
                         if k != "confirmation_count"},
                strength=int(snap.get("strength") or 0),
                probability=int(snap.get("probability") or 50),
            )
            enriched = enrich_chain(match, events, ohlcv)

            new_factors = dict(snap.get("factors") or {})
            new_factors.pop("confirmation_count", None)
            if "confirmation_count" in enriched.factors:
                new_factors["confirmation_count"] = enriched.factors["confirmation_count"]

            changed = (enriched.chain != snap["chain"]) or (new_factors != (snap.get("factors") or {}))
            if not changed:
                continue
            snap["chain"] = enriched.chain
            snap["factors"] = new_factors
            a.snapshot = json.dumps(snap)
            updated += 1

        db.commit()
    print(f"scanned={scanned} updated={updated}")


if __name__ == "__main__":
    main()
