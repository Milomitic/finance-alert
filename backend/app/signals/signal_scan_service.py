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
from app.signals.runner import detect_signals


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


def evaluate_signals(db: Session, stock: Stock, ohlcv: pd.DataFrame) -> int:
    """Detect signals for `stock` and add Alert rows for new ones above the
    confidence threshold. Returns the count added. Caller commits."""
    last_close = float(ohlcv["close"].iloc[-1])
    added = 0
    for m in detect_signals(ohlcv):
        if m.confidence < settings.signal_min_confidence:
            continue
        sig_date = _to_date(m.signal_date)
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
        snapshot = {
            "tone": m.tone, "confidence": m.confidence, "chain": m.chain,
            "factors": m.factors, "invalidation": m.invalidation,
            "sources": getattr(_detector_for(m.name), "sources", []),
        }
        db.add(Alert(
            rule_id=None, stock_id=stock.id, trigger_price=last_close,
            signal_date=sig_date, signal_name=m.name,
            snapshot=json.dumps(snapshot),
        ))
        added += 1
    return added


def _detector_for(name: str):
    # Deferred import: the detectors package imports the signal stack, so a
    # module-level import here would create a cycle at load time. Keep local.
    from app.signals.detectors.registry import DETECTORS
    return next((d for d in DETECTORS if getattr(d, "name", None) == name), None)
