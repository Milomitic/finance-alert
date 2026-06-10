"""Run all active detectors over one ticker's OHLCV -> list[SignalMatch]."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
from loguru import logger

from app.signals.calibration_map import get_calibration
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
                # Regime-conditioned Probabilità (#8): stamp the fire-time
                # regime and, ONLY for detectors whose calibration artifact
                # carries a per-regime base rate, recompute probability with it.
                # Dormant (byte-identical) while no detector has a regime block.
                new_prob = m.probability
                if get_calibration().regime_base_rate(m.name, ctx.regime) is not None:
                    new_prob = get_calibration().probability(
                        m.name, m.factors, regime=ctx.regime
                    )
                m = replace(m, regime=ctx.regime, probability=new_prob)
                out.append(m)
        except Exception as e:  # noqa: BLE001 — one detector must not kill the rest
            logger.warning(f"[signals] detector {getattr(det, 'name', '?')} crashed: {e}")
    return out
