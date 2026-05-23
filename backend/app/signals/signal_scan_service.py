"""Turn detected signals into deduped Alert rows during the scan."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Stock
from app.signals.context import build_context
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


def _follow_through_ok(m, ohlcv: pd.DataFrame, idx_by_date: dict[str, int]):
    # Has the bar AFTER the trigger held the invalidation level? Returns True
    # (confirmed, or nothing to confirm), False (the next bar broke back through
    # the level -> likely fakeout), or None (the signal triggered on the last
    # available bar, so confirmation is pending a later scan).
    inv = m.invalidation or {}
    level = inv.get("level") if isinstance(inv, dict) else None
    if not isinstance(level, (int, float)):
        return True
    si = idx_by_date.get(str(m.signal_date)[:10]) if m.signal_date else None
    if si is None:
        return True
    if si >= len(ohlcv) - 1:
        return None
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
    trend_sign = build_context(ohlcv).trend_sign
    idx_by_date = {str(d)[:10]: i for i, d in enumerate(ohlcv["date"])}
    added = 0
    for m in detect_signals(ohlcv, db=db, stock=stock):
        if m.confidence < settings.signal_min_confidence:
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
            if _follow_through_ok(m, ohlcv, idx_by_date) is not True:
                continue
        sig_date = _to_date(m.signal_date)
        # Recency guard: skip setups that completed long before the latest bar
        # (the ~260-bar window holds a year of history; without this the first
        # scan would surface months-old signals as if fresh).
        if sig_date is not None and last_bar_date is not None \
                and (last_bar_date - sig_date).days > settings.signal_max_age_days:
            continue
        # Dedup: same (stock, signal, signal_date) already emitted -> skip.
        exists = db.execute(
            select(Alert.id).where(
                Alert.stock_id == stock.id,
                Alert.signal_name == m.name,
                Alert.signal_date == sig_date,
            ).limit(1)
        ).scalars().first()
        if exists is not None:
            continue
        ann = {"levels": list(m.annotations.get("levels", [])),
               "points": list(m.annotations.get("points", []))}
        inv = m.invalidation or {}
        inv_level = inv.get("level") if isinstance(inv, dict) else None
        if isinstance(inv_level, (int, float)) and not any(l.get("kind") == "stop" for l in ann["levels"]):
            ann["levels"].append({"label": "Stop / invalidazione", "price": float(inv_level), "kind": "stop"})
        snapshot = {
            "tone": m.tone, "confidence": m.confidence, "chain": m.chain,
            "factors": m.factors, "invalidation": m.invalidation,
            "sources": getattr(_detector_for(m.name), "sources", []),
            "annotations": ann,
        }
        db.add(Alert(
            stock_id=stock.id, trigger_price=last_close,
            signal_date=sig_date, signal_name=m.name,
            snapshot=json.dumps(snapshot),
        ))
        added += 1
    return added


def _detector_for(name: str):
    return next((d for d in DETECTORS if getattr(d, "name", None) == name), None)
