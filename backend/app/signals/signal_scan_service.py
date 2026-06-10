"""Turn detected signals into deduped Alert rows during the scan."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Stock
from app.signals.context import build_context
from app.signals.horizon import classify_horizon
from app.signals.detectors.registry import DETECTORS
from app.signals.runner import detect_signals

# --- Quality gates (reduce false positives) --------------------------------
# Trend-following signals: their direction should agree with the prevailing
# trend. The regime gate (settings.signal_require_trend_alignment) drops these
# when they contradict it. Reversal / mean-reversion / fundamental-driven
# detectors are intentionally excluded -- going against (or being independent
# of) the trend is their purpose.
_TREND_FOLLOWING_SIGNALS = {
    "volume_breakout",
    "high52_momentum",
    "trend_pullback",
    "squeeze_expansion",
    "gap_and_go",
    "adx_confirmation",
    "sr_flip",
    "structure_break",
}


def _to_date(iso: str) -> date | None:
    try:
        return date.fromisoformat(iso[:10])
    except (ValueError, TypeError):
        # A NULL signal_date collapses dedup (all null-dated signals for a
        # stock/name share one slot), so make a parse failure visible rather
        # than silently suppressing real signals. Never fires in practice -
        # signal_date comes from an extractor-produced ISO string.
        logger.warning(f"[signals] could not parse signal_date {iso!r}; storing NULL")
        return None


def _follow_through_ok(m, ohlcv: pd.DataFrame, idx_by_date: dict[str, int]) -> bool:
    # Drop only a CONFIRMED fakeout: the bar AFTER the trigger exists and closed
    # back through the invalidation level. A trigger on the last available bar
    # passes -- it cannot be a confirmed fakeout yet, and many detectors stamp
    # signal_date on the latest bar, so "holding" it would suppress them
    # permanently (the date moves with each scan) instead of by one bar.
    inv = m.invalidation or {}
    level = inv.get("level") if isinstance(inv, dict) else None
    if not isinstance(level, (int, float)):
        return True
    si = idx_by_date.get(str(m.signal_date)[:10]) if m.signal_date else None
    if si is None or si >= len(ohlcv) - 1:
        return True
    next_close = float(ohlcv["close"].iloc[si + 1])
    if m.tone == "bull":
        return next_close >= float(level)
    if m.tone == "bear":
        return next_close <= float(level)
    return True


def evaluate_signals(db: Session, stock: Stock, ohlcv: pd.DataFrame) -> int:
    """Detect signals for `stock` and add Alert rows for new ones above the
    confidence threshold. Returns the count added. Caller commits."""
    last_close = float(ohlcv["close"].iloc[-1])
    last_bar_date = _to_date(str(ohlcv["date"].iloc[-1]))
    # Prevailing trend (EMA200 slope) for the regime gate + a date->row map for
    # the follow-through check. Both computed once per ticker.
    _ctx = build_context(ohlcv)
    trend_sign = _ctx.trend_sign
    # ATR at the signal bar: lets the frontend Trade Playbook anchor the stop
    # floor + target cap to volatility (validated 2026-05-25). NaN-guarded.
    _atr = float(_ctx.atr) if (_ctx.atr is not None and _ctx.atr == _ctx.atr) else None
    idx_by_date = {str(d)[:10]: i for i, d in enumerate(ohlcv["date"])}
    added = 0
    for m in detect_signals(ohlcv, db=db, stock=stock):
        # Emission gate now on Forza (strength). `signal_min_confidence` is the
        # min-Forza bar; note calibrated Forza runs lower than the old confidence,
        # so the same 60 admits fewer, individually-stronger signals (revisit).
        if m.strength < settings.signal_min_confidence:
            continue
        # Step 1 -- regime gate: a trend-following signal must agree with the
        # prevailing trend; contradicting it is the dominant false-positive
        # source. Reversal/fundamental detectors are exempt (see the set above).
        if settings.signal_require_trend_alignment and m.name in _TREND_FOLLOWING_SIGNALS:
            if (m.tone == "bull" and trend_sign < 0) or (m.tone == "bear" and trend_sign > 0):
                continue
        # Step 2 -- follow-through: the bar after the trigger must hold the
        # invalidation level. A fresh last-bar trigger is held for a later scan
        # (None); a fakeout is dropped (False).
        if settings.signal_require_follow_through:
            if not _follow_through_ok(m, ohlcv, idx_by_date):
                continue
        sig_date = _to_date(m.signal_date)
        # Recency guard: skip setups that completed long before the latest bar
        # (the ~260-bar window holds a year of history; without this the first
        # scan would surface months-old signals as if fresh).
        if sig_date is not None and last_bar_date is not None \
                and (last_bar_date - sig_date).days > settings.signal_max_age_days:
            continue
        ann = {"levels": list(m.annotations.get("levels", [])),
               "points": list(m.annotations.get("points", []))}
        inv = m.invalidation or {}
        inv_level = inv.get("level") if isinstance(inv, dict) else None
        if isinstance(inv_level, (int, float)) and not any(l.get("kind") == "stop" for l in ann["levels"]):
            ann["levels"].append({"label": "Stop / invalidazione", "price": float(inv_level), "kind": "stop"})
        snapshot = {
            "tone": m.tone,
            # Two-score model: Forza (pattern strength) + Probabilita (hit-rate
            # "di accadimento"). Legacy snapshots may still carry a `confidence`
            # alias of strength; readers coalesce $.strength/$.confidence for those.
            "strength": m.strength, "probability": m.probability,
            "chain": m.chain,
            "factors": m.factors, "invalidation": m.invalidation,
            "sources": getattr(_detector_for(m.name), "sources", []),
            "annotations": ann, "atr": _atr,
            "horizon": classify_horizon(m.name, m.chain),
            # Fire-time market regime (close vs EMA200) — audit trail for the
            # regime-conditioned Probabilita (#8); null on <200-bar histories.
            "regime_at_fire": m.regime,
        }
        now_iso = datetime.now(UTC).isoformat()
        # Cooldown + refresh dedup. Several "state" detectors stamp signal_date
        # on the LATEST bar, so the same ongoing setup would otherwise mint a new
        # (stock, name, signal_date) every day the condition holds -> a stream of
        # near-duplicate alerts differing only in price. Instead: find the most
        # recent same-(stock, signal) alert; if it shares the direction and sits
        # within the cooldown window, treat this detection as the SAME setup.
        prior = db.execute(
            select(Alert)
            .where(Alert.stock_id == stock.id, Alert.signal_name == m.name)
            .order_by(Alert.signal_date.desc().nullslast(), Alert.triggered_at.desc())
            .limit(1)
        ).scalars().first()
        if prior is not None and _snapshot_tone(prior.snapshot) == m.tone \
                and _within_cooldown(prior.signal_date, sig_date):
            if prior.archived_at is None:
                # Same ongoing setup -> refresh the live alert IN PLACE with the
                # latest recomputed snapshot. The whole snapshot is replaced (not
                # appended), so we mark provenance so a later revision is never
                # mistaken for the original-emission analysis: PRESERVE the
                # original `first_emitted_at` and stamp `amended_at` = now.
                # signal_date + triggered_at advance together (the anchor moves
                # forward) without faking a delayed-detection gap.
                try:
                    _prior_snap = json.loads(prior.snapshot) if prior.snapshot else {}
                except (ValueError, TypeError):
                    _prior_snap = {}
                snapshot["first_emitted_at"] = (
                    _prior_snap.get("first_emitted_at")
                    or (prior.triggered_at.isoformat() if prior.triggered_at else now_iso)
                )
                snapshot["amended_at"] = now_iso
                snapshot["amend_count"] = int(_prior_snap.get("amend_count") or 0) + 1
                prior.trigger_price = last_close
                prior.signal_date = sig_date
                prior.snapshot = json.dumps(snapshot)
                prior.triggered_at = datetime.now(UTC)
            # Archived within the window: respect the user's archive, don't
            # resurrect it. Either way, no new row.
            continue
        # New alert: pin the original emission timestamp (never overwritten by
        # later refreshes), no amendment yet.
        snapshot["first_emitted_at"] = now_iso
        db.add(Alert(
            stock_id=stock.id, trigger_price=last_close,
            signal_date=sig_date, signal_name=m.name,
            snapshot=json.dumps(snapshot),
        ))
        added += 1
    return added


def _snapshot_tone(snapshot_str: str | None) -> str | None:
    """Read the stored tone from an Alert.snapshot JSON blob (None on any
    parse failure -- never raises, so dedup can't be derailed by a bad row)."""
    try:
        return json.loads(snapshot_str).get("tone") if snapshot_str else None
    except (ValueError, TypeError, AttributeError):
        return None


def _within_cooldown(prior_date: date | None, sig_date: date | None) -> bool:
    """True when `sig_date` falls within the dedup cooldown window AFTER
    `prior_date`. Two NULL-dated signals share one slot (legacy exact-match
    behavior); a NULL on only one side never collapses."""
    if prior_date is None or sig_date is None:
        return prior_date is None and sig_date is None
    return 0 <= (sig_date - prior_date).days <= settings.signal_dedup_cooldown_days


def _detector_for(name: str):
    return next((d for d in DETECTORS if getattr(d, "name", None) == name), None)
