"""Signal time-horizon classification (short / medium / long).

Single source of truth shared by the scan (which stamps `horizon` into the
alert snapshot), the confluence service (multi-horizon detection) and the
calibration service. The frontend Trade Playbook READS `snapshot.horizon`
and only falls back to its own copy for legacy alerts -> no drift.

Rule (must mirror frontend `tradePlaybook.ts` classifyHorizon):
  - span of the chain's event dates is the primary signal:
      <= 7 calendar days -> short, <= 35 -> medium, else long.
  - when the chain has fewer than 2 distinct dates, fall back to the detector
    prior (a trend signal is long, a single-candle reversal is short, ...).
"""
from __future__ import annotations

from datetime import date

Horizon = str  # "short" | "medium" | "long"

# Detector -> prior horizon, used when the chain spans a single day.
_PRIOR: dict[str, Horizon] = {
    "high52_momentum": "long", "trend_pullback": "long", "structure_break": "long",
    "adx_confirmation": "long", "pead": "long", "analyst_momentum": "long",
    "insider_buy": "long",
    "sr_flip": "medium", "volume_breakout": "medium", "squeeze_expansion": "medium",
    "rsi_divergence": "medium", "macd_divergence": "medium", "hidden_divergence": "medium",
    "oversold_reversal": "medium", "chart_pattern": "medium",
    "candle_reversal": "short", "gap_and_go": "short",
}


def _parse(d: object) -> date | None:
    if isinstance(d, str) and len(d) >= 10:
        try:
            return date.fromisoformat(d[:10])
        except ValueError:
            return None
    return None


def classify_horizon(name: str | None, chain: list[dict] | None) -> Horizon:
    """Return 'short' | 'medium' | 'long' for a signal from its chain span
    (primary) + detector prior (fallback)."""
    # Co-temporal confirmation steps (kind="confirmation") are appended near the
    # signal bar by chain_enrichment; they must NOT pull the span in and shift
    # the timeframe label. Span over the detector's own cause steps only.
    cause = [c for c in (chain or []) if c.get("kind") != "confirmation"]
    dates = sorted({d for d in (_parse(c.get("date")) for c in cause) if d is not None})
    if len(dates) >= 2:
        span = (dates[-1] - dates[0]).days
        return "short" if span <= 7 else "medium" if span <= 35 else "long"
    return _PRIOR.get(name or "", "medium")
