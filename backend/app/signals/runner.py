"""Run all active detectors over one ticker's OHLCV -> signals (+ setups)."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
from loguru import logger

from app.signals.calibration_map import get_calibration
from app.signals.chain_enrichment import enrich_chain
from app.signals.context import SignalContext, build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.registry import DETECTORS
from app.signals.events_fundamental import gather_events
from app.signals.setups.base import SetupMatch


def detect_signals(ohlcv: pd.DataFrame, *, db=None, stock=None) -> list[SignalMatch]:
    """Unchanged contract — every existing caller keeps getting just signals."""
    return detect_signals_and_setups(ohlcv, db=db, stock=stock)[0]


def detect_signals_and_setups(
    ohlcv: pd.DataFrame, *, db=None, stock=None, ctx: SignalContext | None = None,
) -> tuple[list[SignalMatch], list[SetupMatch]]:
    """Signals AND pre-trigger setups from ONE feature build.

    Sharing the build matters: `gather_events` + `build_context` are the
    expensive part, and running a second pass per stock would double that
    across the ~1000-name universe for information the first pass already had
    in hand.

    A detector opts into setups by implementing `proximity()`; those that
    don't simply contribute none. Nothing here can change what `detect()`
    returns, so the signal path and the outcome warehouse are untouched.

    ⚠️ FA-065 — `ctx` lets the caller hand over the context it already built.
    `evaluate_signals` builds one for its own gates (trend sign, ATR) and then
    called this, which built a SECOND one from the same DataFrame: the docstring
    above said sharing the build was the point, and the scan path did not share
    it. Two owners of one computation diverge — the duplicated Tecnico row
    between `finalize` and `recompute_one` already produced a 500 in production
    that way. Passing it is optional so every other caller keeps its contract;
    `test_un_contesto_per_titolo` pins that the result is byte-identical.
    """
    if ohlcv is None or len(ohlcv) < 2:
        return [], []
    try:
        events = gather_events(ohlcv, db=db, stock=stock)
        if ctx is None:
            ctx = build_context(ohlcv)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[signals] feature build failed: {e}")
        return [], []
    out: list[SignalMatch] = []
    setups: list[SetupMatch] = []
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

        # Setups are strictly secondary: a crash here must never cost a signal.
        prox = getattr(det, "proximity", None)
        if prox is None:
            continue
        try:
            sm = prox(events, ohlcv, ctx)
            if sm is not None:
                setups.append(sm)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[setups] {getattr(det, 'name', '?')} proximity crashed: {e}")
    return out, setups
