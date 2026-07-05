"""Shared substrate of the score_service package: pillar weights, static
sector benchmarks, ramp/blend scoring curves and the component-aggregation
machinery (the heart of the missing-data-neutralization story).

Everything here is pure (no DB, no network) — the modules that compute
pillars, risk and the composite all build on these primitives.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.services.sector_stats_service import SectorStatsBundle


# ---------------------------------------------------------------------------
# Pillar weights (composite-level) and risk tier set.
# ---------------------------------------------------------------------------

# V4 — PURE-FUNDAMENTAL composite (3-lens cleanup, 2026-05): the Momentum
# pillar was REMOVED. Price-action (trend / momentum / structure / RSI / MACD)
# is the job of the separate TechnicalScore lens; mixing a 0.20 momentum pillar
# into the "is this a good company?" score double-counted that lens and muddied
# the question. The 5 remaining fundamental pillars are renormalised to 1.0
# (old 0.80 base ÷ itself), preserving their relative ordering:
#   - Profitability: 0.19 (was 0.15)
#   - Sustainability: 0.19 (was 0.15)
#   - Growth:        0.28 (was 0.23)
#   - Value:         0.16 (was 0.13)
#   - Sentiment:     0.18 (was 0.14)
# Total = 1.00. (Momentum 0.20 dropped → lives only in TechnicalScore.)
PILLAR_WEIGHTS: dict[str, float] = {
    "profitability": 0.19,
    "sustainability": 0.19,
    "growth": 0.28,
    "value": 0.16,
    "sentiment": 0.18,
}

RISK_TIERS: tuple[str, ...] = ("conservative", "moderate", "aggressive")

# Static V1 sector P/E medians, kept verbatim. Universe-wide fallback ~22.
_SECTOR_PE_MEDIAN: dict[str, float] = {
    "Technology": 28.0,
    "Financial Services": 14.0,
    "Financials": 14.0,
    "Utilities": 22.0,
    "Healthcare": 22.0,
    "Health Care": 22.0,
    "Consumer Defensive": 24.0,
    "Consumer Staples": 24.0,
    "Consumer Cyclical": 25.0,
    "Consumer Discretionary": 25.0,
    "Industrials": 22.0,
    "Energy": 14.0,
    "Basic Materials": 16.0,
    "Materials": 16.0,
    "Communication Services": 22.0,
    "Real Estate": 30.0,
}
_UNIVERSE_PE_MEDIAN = 22.0

# Sector P/B medians — used for the value pillar's price-to-book lane.
# Approximate broad-market values; refined per-period in V3.
_SECTOR_PB_MEDIAN: dict[str, float] = {
    "Technology": 6.0,
    "Financial Services": 1.3,
    "Financials": 1.3,
    "Utilities": 1.8,
    "Healthcare": 4.0,
    "Health Care": 4.0,
    "Consumer Defensive": 4.0,
    "Consumer Staples": 4.0,
    "Consumer Cyclical": 3.5,
    "Consumer Discretionary": 3.5,
    "Industrials": 3.0,
    "Energy": 1.8,
    "Basic Materials": 2.0,
    "Materials": 2.0,
    "Communication Services": 3.0,
    "Real Estate": 2.0,
}
_UNIVERSE_PB_MEDIAN = 3.0

# Defensive/cyclical sectors for the risk classifier.
_DEFENSIVE_SECTORS = {
    "Utilities", "Consumer Defensive", "Consumer Staples",
    "Healthcare", "Health Care",
}
_CYCLICAL_SECTORS = {
    "Technology", "Consumer Cyclical", "Consumer Discretionary",
    "Energy", "Basic Materials", "Materials",
}

_MEGA_CAP_THRESHOLD = 200_000_000_000.0


class RecomputeCancelled(Exception):
    """Raised by recompute_all when the cancel_check callback returns True.

    The runner (score_runner.run_tracked_recompute) catches it and marks
    the associated ScanRun as failed with a user-friendly message — same
    pattern as ScanCancelled in scan_service."""


# ---------------------------------------------------------------------------
# Generic helpers.
# ---------------------------------------------------------------------------

def _is_finite(x: Any) -> bool:
    """True iff x is a finite real number (not None, not NaN, not Inf)."""
    if x is None:
        return False
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def _ramp(value: float, *, full: float, zero: float, max_score: float = 100.0) -> float:
    """Two-point linear ramp returning a 0..max_score signal score.

    `full > zero`  → "higher is better": value≥full → max, value≤zero → 0.
    `full < zero`  → "lower is better":  value≤full → max, value≥zero → 0.
    """
    if full == zero:
        return max_score if value == full else 0.0
    if full > zero:
        if value >= full:
            return max_score
        if value <= zero:
            return 0.0
        return max_score * (value - zero) / (full - zero)
    if value <= full:
        return max_score
    if value >= zero:
        return 0.0
    return max_score * (zero - value) / (zero - full)


def _ramp3(value: float, *, full: float, half: float, zero: float, max_score: float = 100.0) -> float:
    """Three-point piecewise-linear ramp: full / half / zero → max / max/2 / 0.

    Two segments: zero-to-half maps to [0, max/2]; half-to-full maps to
    [max/2, max]. Works in both orientations (full > zero or full < zero).
    """
    half_score = max_score / 2.0
    higher_is_better = full > zero
    if higher_is_better:
        if value >= full:
            return max_score
        if value <= zero:
            return 0.0
        if value >= half:
            return half_score + (max_score - half_score) * (value - half) / (full - half)
        return half_score * (value - zero) / (half - zero)
    # lower-is-better
    if value <= full:
        return max_score
    if value >= zero:
        return 0.0
    if value <= half:
        return half_score + (max_score - half_score) * (half - value) / (half - full)
    return half_score * (zero - value) / (zero - half)


def _safe_round(x: float, digits: int = 2) -> float:
    """Round to `digits`, clamping non-finite to 0.0 — JSON cannot serialise NaN/Inf."""
    if not _is_finite(x):
        return 0.0
    return round(float(x), digits)


# ---------------------------------------------------------------------------
# Component machinery — the heart of the missing-data-neutralization story.
# ---------------------------------------------------------------------------

@dataclass
class _Component:
    """One signal feeding a pillar.

    `score` is the 0-100 score for this signal (None when input was
    unavailable). `weight` is the relative weight WITHIN the pillar.
    `raw` is the original numeric input value (or string for special
    formats like "moderate"), retained for the breakdown JSON so the
    UI can render the actual number alongside the score.

    `sector_median` is the peer-group median used by the sector-aware
    blended scoring. None when no sector benchmark was available
    (thin sector, missing data, or non-aggregatable attribute like
    overall_risk). Surfaced in the breakdown so the UI can show a
    "vs peers" tooltip without breaking the scalar `raw` shape.
    """
    name: str
    raw: Any
    score: float | None
    weight: float
    sector_median: float | None = None


def _aggregate(components: list[_Component]) -> tuple[float | None, float, dict[str, Any]]:
    """Combine components into a pillar score with missing-data neutralization.

    Each component contributes (score * weight) to the numerator and (weight)
    to the denominator IFF its score is not None. Missing components are
    excluded from BOTH — they don't drag the average down.

    Returns (pillar_score_0_100 | None, max_pts=100.0, breakdown_dict).
    `pillar_score = None` when every component is missing → caller treats
    this as "drop this pillar from the composite".

    The breakdown dict echoes each component's raw value, score, weight, and
    a `present` boolean. The UI renders missing components as "—" and uses
    `present` to compute the pillar's effective weight visualization.
    """
    breakdown: dict[str, Any] = {}
    num = 0.0
    den = 0.0
    n_present = 0
    for c in components:
        present = c.score is not None
        if present:
            num += float(c.score) * c.weight  # type: ignore[arg-type]
            den += c.weight
            n_present += 1
        # raw_out: keep finite values; None / NaN / Inf collapse to None so
        # the breakdown is JSON-serialisable with allow_nan=False.
        raw_out: Any
        if c.raw is None:
            raw_out = None
        elif isinstance(c.raw, (int, float)):
            raw_out = _safe_round(float(c.raw), 4) if _is_finite(c.raw) else None
        else:
            raw_out = c.raw
        breakdown[c.name] = {
            "raw": raw_out,
            "score": _safe_round(c.score, 2) if c.score is not None else None,
            "weight": _safe_round(c.weight, 4),
            "present": present,
            "sector_median": (
                _safe_round(c.sector_median, 4)
                if c.sector_median is not None and _is_finite(c.sector_median)
                else None
            ),
        }
    if n_present == 0 or den <= 0:
        return None, 100.0, {}
    pillar = num / den
    weight_sum_total = sum(c.weight for c in components)
    breakdown["_meta"] = {
        "components_present": n_present,
        "components_total": len(components),
        "weight_sum_present": _safe_round(den, 4),
        "weight_sum_total": _safe_round(weight_sum_total, 4),
        # Fraction of this pillar's nominal component weight that had
        # data. 1.0 = fully covered; low values mean the pillar score
        # rests on few inputs and is renormalised over a thin base —
        # the consumer should trust it less (QW5 confidence signal).
        "coverage": _safe_round(
            den / weight_sum_total if weight_sum_total > 0 else 0.0, 4
        ),
    }
    return _safe_round(pillar, 2), 100.0, breakdown


# ---------------------------------------------------------------------------
# Sector-relative blending helpers.
# ---------------------------------------------------------------------------
#
# Per-attribute scoring blends two signals 50/50 by default:
#
#   1. Absolute score: `_ramp3` against canonical thresholds (e.g. ROE
#      ≥20% → full, 10% → half, 0% → zero). Captures "is this a good
#      business in absolute terms?"
#
#   2. Sector-relative score: `_ramp3` against the diff/ratio between
#      the stock's value and its sector's median peer. Captures "is
#      this a good business *for its peer group*?"
#
# Why blend, not replace? An attribute with a peer-relative score of
# 100 (massively above sector median) but absolute score of 0 (e.g.
# ROE -2% in a sector with median -8%) gets a final ~50, not 100.
# The absolute floor prevents "least sick patient in a hospice" from
# scoring higher than it should.
#
# When the sector median is missing (`sector_stats=None` or thin
# sector below the min-N gate), we fall back to absolute-only — same
# behavior as V2 pre-sector-aware.

_BLEND_ALPHA = 0.5  # weight on absolute score (1-alpha goes to relative)


def _blended_hib(
    value: Any,
    sector_med: float | None,
    *,
    abs_full: float,
    abs_half: float,
    abs_zero: float,
    rel_full_pp: float,
    rel_half_pp: float = 0.0,
    rel_zero_pp: float | None = None,
) -> float | None:
    """Higher-is-better blend.

    rel_*_pp are signed diffs (stock_value − sector_median) measured in
    the same units as the attribute. e.g. for ROE (a fraction), rel_full
    of +0.05 means "scored full when ROE is at least 5pp above peer
    median". rel_zero_pp defaults to -rel_full_pp (symmetric).
    """
    if not _is_finite(value):
        return None
    abs_s = _ramp3(float(value), full=abs_full, half=abs_half, zero=abs_zero)
    if sector_med is None or not _is_finite(sector_med):
        return abs_s
    if rel_zero_pp is None:
        rel_zero_pp = -rel_full_pp
    diff = float(value) - float(sector_med)
    rel_s = _ramp3(diff, full=rel_full_pp, half=rel_half_pp, zero=rel_zero_pp)
    return _BLEND_ALPHA * abs_s + (1.0 - _BLEND_ALPHA) * rel_s


def _blended_lib(
    value: Any,
    sector_med: float | None,
    *,
    abs_full: float,
    abs_half: float,
    abs_zero: float,
    rel_full_pp: float,
    rel_half_pp: float = 0.0,
    rel_zero_pp: float | None = None,
) -> float | None:
    """Lower-is-better blend (e.g. debt/equity in pp scale).

    Mirror of `_blended_hib` — `rel_full_pp` should be NEGATIVE (e.g.
    -50 for debt/equity = "full when 50pp below sector"). Symmetric
    default for `rel_zero_pp` is +abs(rel_full_pp).
    """
    if not _is_finite(value):
        return None
    abs_s = _ramp3(float(value), full=abs_full, half=abs_half, zero=abs_zero)
    if sector_med is None or not _is_finite(sector_med):
        return abs_s
    if rel_zero_pp is None:
        rel_zero_pp = -rel_full_pp
    diff = float(value) - float(sector_med)
    rel_s = _ramp3(diff, full=rel_full_pp, half=rel_half_pp, zero=rel_zero_pp)
    return _BLEND_ALPHA * abs_s + (1.0 - _BLEND_ALPHA) * rel_s


def _blended_lib_multiple(
    value: Any,
    sector_med: float | None,
    *,
    abs_full: float,
    abs_half: float,
    abs_zero: float,
) -> float | None:
    """Lower-is-better blend for multiples (P/E, P/B, P/S, EV/EBITDA, …).

    Sector-relative scoring uses the ratio (stock / sector_med) rather
    than a signed diff because multiples span orders of magnitude:
        ratio ≤ 0.7  → 100 (significantly cheaper than peers)
        ratio = 1.0  → 50  (par with peers)
        ratio ≥ 1.5  → 0   (significantly more expensive)
    Linear in between. Negative or zero values short-circuit to None
    (the absolute lane already handles these).
    """
    if not _is_finite(value) or value is None or float(value) <= 0:
        return None
    val = float(value)
    abs_s = _ramp3(val, full=abs_full, half=abs_half, zero=abs_zero)
    if (
        sector_med is None
        or not _is_finite(sector_med)
        or float(sector_med) <= 0
    ):
        return abs_s
    ratio = val / float(sector_med)
    if ratio <= 0.7:
        rel_s = 100.0
    elif ratio <= 1.0:
        rel_s = 100.0 - (ratio - 0.7) / 0.3 * 50.0
    elif ratio <= 1.5:
        rel_s = 50.0 - (ratio - 1.0) / 0.5 * 50.0
    else:
        rel_s = 0.0
    return _BLEND_ALPHA * abs_s + (1.0 - _BLEND_ALPHA) * rel_s


def _resolve_med(sector_stats: SectorStatsBundle | None, sector: str | None, field: str) -> float | None:
    """Tiny convenience wrapper for the resolve-or-None pattern used in
    every Q/G/V lane. Keeps the call sites readable."""
    if sector_stats is None:
        return None
    return sector_stats.resolve(sector, field)
