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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, ScanRun, StockSetup
from app.models.stock_setup import STATUS_ACTIVE, STATUS_CONVERTED, STATUS_EXPIRED
from app.signals.setups.base import SetupMatch, convenience

# A setup not re-observed for this many days is stale: the conditions decayed
# without firing. Short on purpose — a setup is a "watch this now" object, and
# one kept alive for weeks is just clutter that inflates the active list.
_EXPIRE_AFTER_DAYS = 10

# Absolute ceiling on how long a setup may stay pending, measured from
# `first_seen_at` and independent of re-observation.
#
# WHY THIS IS NEEDED. `_EXPIRE_AFTER_DAYS` above measures staleness from
# `last_seen_at`, which every scan refreshes while the conditions still hold —
# so a setup whose conditions persist never expires at all. Measured on
# 2026-08-26: 1,420 active setups, 715 of them `oversold_reversal`, none of
# which had ever resolved. "Oversold and within 8% of a support" is a state a
# stock can sit in for months, and the row sat there with it.
#
# WHY 28. The lead time of every conversion so far: 26% within 3 days, 32% by
# a week, 82% by 13 days, then 12% and 5.5% in the last two bands. Nothing has
# converted past 27 days — but that figure is CENSORED, because the feature
# itself is only 28 days old and no setup has yet had the chance. So the cap is
# justified by the shape of the decline, not by the empty tail: a setup still
# waiting after four weeks is not providing lead time any more, it is
# describing a condition. Revisit once there is a longer history to read.
_MAX_AGE_DAYS = 28
# Scans run twice a day, so a healthy 10-day window contains ~20. Requiring a
# handful means a brief outage cannot silently retire the whole list.
_MIN_SCANS_BEFORE_EXPIRY = 3


def upsert_setup(
    db: Session,
    *,
    stock_id: int,
    match: SetupMatch,
    technical_composite: float | None = None,
    quality_composite: float | None = None,
) -> StockSetup | None:
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

    # Emission gate. Without it the first production scan produced 1214 setups
    # over ~1000 stocks — the whole market, not a watchlist. A setup below the
    # bar is not merely hidden: an EXISTING row that decays below it is
    # dropped, so a list that stops deserving attention actually shrinks
    # instead of accumulating forever.
    if score < settings.setup_min_convenience:
        if row is not None and row.status == STATUS_ACTIVE:
            db.delete(row)
        return None

    if row is None:
        row = StockSetup(
            stock_id=stock_id,
            detector=match.detector,
            tone=match.tone,
            proximity=match.proximity,
            distance_atr=match.distance_atr,
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
    row.distance_atr = match.distance_atr
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

    GUARDED on scans actually having run. `last_seen_at` only advances when a
    scan re-observes the setup, so a stretch with no successful scan — the app
    down, a crashing job, the OHLCV outage of July 2026 — looks identical to
    "the conditions decayed". Ageing setups out during a pipeline problem
    would inflate the expired count and make the feature look worse than it
    is, which is the mirror image of the failure the no-delete rule prevents.
    """
    cutoff = datetime.combine(
        (today or date.today()) - timedelta(days=_EXPIRE_AFTER_DAYS),
        datetime.min.time(),
        tzinfo=UTC,
    )
    # A setup can only be judged stale if scans have had the chance to
    # re-observe it. Require at least this many successful scans since the
    # cutoff, so a quiet pipeline never ages anything out.
    scans_since = db.execute(
        select(func.count())
        .select_from(ScanRun)
        .where(ScanRun.status == "success", ScanRun.completed_at >= cutoff)
    ).scalar_one()
    if scans_since < _MIN_SCANS_BEFORE_EXPIRY:
        logger.info(
            f"[setups] only {scans_since} successful scans since the cutoff — "
            "skipping expiry so a quiet pipeline is not read as decay"
        )
        return 0

    age_cutoff = datetime.combine(
        (today or date.today()) - timedelta(days=_MAX_AGE_DAYS),
        datetime.min.time(),
        tzinfo=UTC,
    )
    rows = db.execute(
        select(StockSetup).where(StockSetup.status == STATUS_ACTIVE)
    ).scalars().all()
    n_stale = 0
    n_aged = 0
    for row in rows:
        seen = row.last_seen_at
        if seen is not None and seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        first = row.first_seen_at
        if first is not None and first.tzinfo is None:
            first = first.replace(tzinfo=UTC)

        stale = seen is not None and seen < cutoff
        # Aged out while still perfectly valid: the conditions never decayed,
        # they simply never resolved either. Counted separately because the
        # two say different things about the detector — decay is the market
        # moving on, age is a gate that describes a state rather than a lead.
        aged = first is not None and first < age_cutoff

        if stale or aged:
            row.status = STATUS_EXPIRED
            row.resolved_at = datetime.now(UTC)
            if stale:
                n_stale += 1
            else:
                n_aged += 1
    if n_stale or n_aged:
        logger.info(
            f"[setups] expired {n_stale + n_aged} setups "
            f"({n_stale} stale, {n_aged} past the {_MAX_AGE_DAYS}-day ceiling)"
        )
    return n_stale + n_aged


def conversion_stats(db: Session) -> dict:
    """The feature's own report card. Read-only, no market claim."""
    # Only setups that were actually SURFACED. A setup the user never saw made
    # no claim to them, so counting its outcome would measure something the
    # feature never offered.
    rows = db.execute(
        select(StockSetup).where(StockSetup.shortlisted.is_(True))
    ).scalars().all()
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


def prune_to_top_per_detector(db: Session) -> int:
    """Keep only the strongest N active setups per (detector, tone).

    The floor alone leaves the list lopsided: `squeeze_expansion` matched 291
    names on the first real scan, because ~30% of any universe has compressed
    bands at any moment. Without a cap one common pattern buries the rarer,
    more specific ones — and the rare ones are the reason to look.

    Runs AFTER the scan because the ranking is only knowable once every stock
    has been evaluated.

    Dropped rows are FLAGGED, never deleted. Deleting them looked tidy and was
    a bug: `first_seen_at` would go with them, so a setup hovering at the cap
    boundary would restart its wait each time it re-entered, quietly zeroing
    `lead_days` — the one number this feature is judged by. The row survives,
    keeps its history, and simply stops being surfaced.
    """
    rows = db.execute(
        select(StockSetup).where(StockSetup.status == STATUS_ACTIVE)
    ).scalars().all()
    by_group: dict[tuple[str, str], list[StockSetup]] = {}
    for r in rows:
        by_group.setdefault((r.detector, r.tone), []).append(r)

    dropped = 0
    for group in by_group.values():
        group.sort(key=lambda r: r.convenience, reverse=True)
        for rank, r in enumerate(group):
            keep = rank < settings.setup_max_per_detector
            if r.shortlisted != keep:
                r.shortlisted = keep
                if not keep:
                    dropped += 1
    if dropped:
        logger.info(f"[setups] {dropped} dropped out of the per-detector shortlist")
    return dropped
