"""Setup = a detector's conditions CONVERGING, before its trigger fires.

WHY THIS IS NOT A SIGNAL
────────────────────────
Every detector is a chain of gates. `oversold_reversal` is the clearest case:

    1. an RSI extreme exists
    2. price sits within 3% of a confirmed S/R level
    3. the last bar TURNED (close >= open for a bull reversal)

Gates 1-2 describe a state that persists for DAYS. Gate 3 is the trigger, and
it fires exactly when the move has already started — which is why signals
arrive with no time to plan a position. The lead time was never missing: it
was computed and thrown away.

A Setup exposes that discarded state. It is a fact about TODAY ("oversold, at
support, has not turned yet"), not a forecast. That distinction is the whole
design:

- It lives in its own table with its own lifecycle. Signals mean "condition
  matched on bar X"; putting a not-yet-matched thing in the same place would
  corrupt `signal_outcomes`, the single source of truth for forward hits.
- It carries NO probability. Probabilità is a per-detector base rate measured
  on FIRED signals; a setup has no such base rate until its own outcomes are
  labelled. Claiming one would repeat the exact error three studies
  (confirmation-count on 14.5k signals, factor-adjustment on 247k, score-IC on
  20k observations) were built to prevent.
- `convenience` below is an ATTENTION/ORDERING score, not a forecast. See its
  docstring.

What a setup does promise is measurable without predicting anything: how often
setups convert into signals, and with how much lead time. `setup_service`
records both.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import clamp01
from app.signals.events import Event


@dataclass
class SetupMatch:
    """A detector's pre-trigger state."""

    detector: str
    tone: str
    # 0..1 — how much of the detector's gate chain is already satisfied. 1.0 is
    # NOT reachable: at 1.0 the detector would have fired and this would be a
    # signal instead.
    proximity: float
    # Plain-language statement of what still has to happen. This is the whole
    # user-facing value: it says what to watch for, so the wait is actionable.
    missing: str
    factors: dict[str, float] = field(default_factory=dict)
    # Chart levels worth drawing while waiting (same shape signals use).
    annotations: dict = field(default_factory=dict)


class SupportsProximity(Protocol):
    """Detectors opt IN by implementing this. Purely additive — `detect()` is
    untouched, so the fired-signal path and the outcome warehouse behave
    exactly as before. A detector without `proximity` simply yields no setups.
    """

    name: str

    def proximity(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext
    ) -> SetupMatch | None: ...


# ─── Convenience: an ordering criterion, NOT a forecast ─────────────────────
# The user's framing: "combinations of extremely favourable conditions —
# panic sell + strong technicals + a bounce at an important level".
#
# That intuition is allowed to drive this score COMPLETELY, with no study
# behind it, for one reason: convenience only decides what you look at first.
# It never touches Forza, never touches Probabilità, and is never presented as
# odds. The asymmetry is the cost of being wrong — a wrong Probabilità gets
# believed and sized on; a wrong ordering costs thirty seconds of attention.
#
# If months of accrued outcomes later show this ordering really does front-run
# the winners, THEN it can be promoted into scoring, with the evidence in hand.
# Until then it ranks, and says nothing.
_W_PROXIMITY = 0.40      # how close to the trigger — the lead-time component
_W_SETUP_QUALITY = 0.35  # how extreme the setup's own factors are
_W_TECHNICAL = 0.15      # the Tecnico lens: posture of the underlying
_W_QUALITY = 0.10        # the Qualità lens: the cross-lens part of the idea


def convenience(
    setup: SetupMatch,
    *,
    technical_composite: float | None = None,
    quality_composite: float | None = None,
) -> float:
    """0..100 attention score. Read the module note above before weighting it
    into anything that claims predictive power — it is not built for that."""
    # The setup's own strength = mean of its non-gate factors. Gates are always
    # 1.0 by construction and would just inflate a constant into the mean.
    strengths = [v for k, v in setup.factors.items() if not k.startswith("gate_")]
    setup_quality = sum(strengths) / len(strengths) if strengths else 0.0

    total = _W_PROXIMITY * clamp01(setup.proximity) + _W_SETUP_QUALITY * clamp01(setup_quality)
    weight = _W_PROXIMITY + _W_SETUP_QUALITY

    # Lens contributions are OPTIONAL: a stock with no technical/quality score
    # must not be pushed down the list for missing data it never had. Renormalise
    # over the weights actually present instead.
    if technical_composite is not None:
        total += _W_TECHNICAL * clamp01(technical_composite / 100.0)
        weight += _W_TECHNICAL
    if quality_composite is not None:
        total += _W_QUALITY * clamp01(quality_composite / 100.0)
        weight += _W_QUALITY

    return round(100.0 * total / weight, 1) if weight else 0.0
