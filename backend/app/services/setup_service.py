"""Setup lifecycle: detect → persist → convert or expire.

The conversion bookkeeping here is the honest core of the feature. Setups make
no claim about the market, so they cannot be validated the way a signal is.
What they CAN be measured on is whether they do what they say:

    conversion rate = converted / (converted + expired)
    lead time       = days between first_seen and the detector firing

If the conversion rate is near zero, setups are noise. If `lead_days` trends
to 0, they are not buying any time and the feature has failed on its own terms.
Both come for free from the lifecycle — no market prediction involved — which
is what lets this ship before any study exists.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, StockSetup
from app.models.stock_setup import STATUS_ACTIVE, STATUS_CONVERTED, STATUS_EXPIRED
from app.signals.setups.base import SetupMatch, convenience

# A setup not re-observed for this many days is stale: the conditions decayed
# without firing. Short on purpose — a setup is a "watch this now" object, and
# one kept alive for weeks is just clutter that inflates the active list.
_EXPIRE_AFTER_DAYS = 10


def upsert_setup(
    db: Session,
    *,
    stock_id: int,
    match: SetupMatch,
    technical_composite: float | None = None,
    quality_composite: float | None = None,
) -> StockSetup:
    """Create or refresh the live setup for (stock, detector).

    UPDATES rather than inserts when one already exists: `first_seen_at` must
    keep pointing at the start of the wait, because that is what `lead_days`
    is measured from. Re-inserting would silently reset the very number this
    feature exists to report.
    """
    now = datetime.now(UTC)
    score = convenience(
        match,
        technical_composite=technical_composite,
        quality_composite=quality_composite,
    )
    row = db.execute(
        select(StockSetup).where(
            StockSetup.stock_id == stock_id, StockSetup.detector == match.detector
        )
    ).scalar_one_or_none()

    if row is None:
        row = StockSetup(
            stock_id=stock_id,
            detector=match.detector,
            tone=match.tone,
            proximity=match.proximity,
            convenience=score,
            missing=match.missing,
            factors_json=json.dumps(match.factors),
            annotations_json=json.dumps(match.annotations),
            status=STATUS_ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(row)
        return row

    # A resolved row that re-forms starts a NEW wait — otherwise a setup that
    # converted in March and re-appears in July would report a 4-month lead.
    if row.status != STATUS_ACTIVE:
        row.status = STATUS_ACTIVE
        row.first_seen_at = now
        row.resolved_at = None
        row.converted_alert_id = None
        row.lead_days = None

    row.tone = match.tone
    row.proximity = match.proximity
    row.convenience = score
    row.missing = match.missing
    row.factors_json = json.dumps(match.factors)
    row.annotations_json = json.dumps(match.annotations)
    row.last_seen_at = now
    return row


def convert_setups_for_alert(db: Session, alert: Alert) -> StockSetup | None:
    """Mark the matching live setup as converted when its detector fires.

    Called with each freshly-created alert. `lead_days` is measured from
    `first_seen_at` — the realised warning this setup gave.
    """
    detector = alert.signal_name
    if detector is None or alert.stock_id is None:
        return None
    row = db.execute(
        select(StockSetup).where(
            StockSetup.stock_id == alert.stock_id,
            StockSetup.detector == detector,
            StockSetup.status == STATUS_ACTIVE,
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    now = datetime.now(UTC)
    first = row.first_seen_at
    if first is not None and first.tzinfo is None:
        first = first.replace(tzinfo=UTC)
    row.status = STATUS_CONVERTED
    row.resolved_at = now
    row.converted_alert_id = alert.id
    row.lead_days = max(0, (now - first).days) if first else None
    logger.info(
        f"[setups] {detector} on stock {alert.stock_id} converted "
        f"after {row.lead_days}d of warning"
    )
    return row


def expire_stale_setups(db: Session, *, today: date | None = None) -> int:
    """Retire live setups whose conditions decayed without firing.

    These are NOT deleted: an expired setup is half of the conversion rate.
    Deleting them would leave only the successes on record and make the
    feature look better than it is.
    """
    cutoff = datetime.combine(
        (today or date.today()) - timedelta(days=_EXPIRE_AFTER_DAYS),
        datetime.min.time(),
        tzinfo=UTC,
    )
    rows = db.execute(
        select(StockSetup).where(StockSetup.status == STATUS_ACTIVE)
    ).scalars().all()
    n = 0
    for row in rows:
        seen = row.last_seen_at
        if seen is not None and seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        if seen is not None and seen < cutoff:
            row.status = STATUS_EXPIRED
            row.resolved_at = datetime.now(UTC)
            n += 1
    if n:
        logger.info(f"[setups] expired {n} stale setups")
    return n


def conversion_stats(db: Session) -> dict:
    """The feature's own report card. Read-only, no market claim."""
    rows = db.execute(select(StockSetup)).scalars().all()
    converted = [r for r in rows if r.status == STATUS_CONVERTED]
    expired = [r for r in rows if r.status == STATUS_EXPIRED]
    resolved = len(converted) + len(expired)
    leads = [r.lead_days for r in converted if r.lead_days is not None]
    return {
        "active": sum(1 for r in rows if r.status == STATUS_ACTIVE),
        "converted": len(converted),
        "expired": len(expired),
        # None (not 0.0) while nothing has resolved yet: a rate computed over
        # an empty denominator is not "0%", it is "unknown", and showing 0%
        # would read as "setups never work".
        "conversion_rate": round(len(converted) / resolved, 3) if resolved else None,
        "avg_lead_days": round(sum(leads) / len(leads), 1) if leads else None,
    }
