"""Run all active detectors over one ticker's OHLCV -> list[SignalMatch]."""
from __future__ import annotations

import pandas as pd
from loguru import logger

from app.signals.chain_enrichment import enrich_chain
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.registry import DETECTORS
from app.signals.events_fundamental import gather_events


def detect_signals(ohlcv: pd.DataFrame, *, db=None, stock=None) -> list[SignalMatch]:
    if ohlcv is None or len(ohlcv) < 2:
        return []
    try:
        events = gather_events(ohlcv, db=db, stock=stock)
        ctx = build_context(ohlcv)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[signals] feature build failed: {e}")
        return []
    out: list[SignalMatch] = []
    for det in DETECTORS:
        try:
            m = det.detect(events, ohlcv, ctx)
            if m is not None:
                # Append co-temporal same-tone confirmations already in the
                # event stream to the match's Catena (display + evidence; the
                # score is unchanged in Phase 1).
                m = enrich_chain(m, events, ohlcv)
                out.append(m)
        except Exception as e:  # noqa: BLE001 — one detector must not kill the rest
            logger.warning(f"[signals] detector {getattr(det, 'name', '?')} crashed: {e}")
    return out
