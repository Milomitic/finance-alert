"""Composite stock-scoring service (V2 — comprehensive + missing-data neutral).

Per-stock 0-100 score from 5 sub-scores: Quality, Growth, Value, Momentum,
Sentiment. The DB row schema (StockScore.composite/quality/growth/value/
momentum/sentiment/risk_tier/breakdown) is unchanged from V1.

What's different from V1
------------------------

1. **Comprehensive coverage.** Each pillar now consumes a much richer set of
   inputs from MicroData / Fundamentals / OHLCV / cached news, instead of
   the 3-5 inputs V1 used. See per-pillar docstrings for the full list.

2. **Missing-data neutralization.** V1 awarded zero points for any missing
   component but kept its weight in the denominator — so a stock with no
   PEG ratio (a data gap, not a quality issue) lost 30% of its Value
   pillar. V2 changes this: a component whose input is missing/None is
   excluded from BOTH numerator and denominator. The pillar score is the
   weighted average of only the components we actually have data for.

   Algorithm (per pillar):
       pillar_score = sum(score_i * weight_i for i in present)
                    / sum(weight_i           for i in present)
   where score_i ∈ [0, 100] and weight_i is a relative weight.
   If no components are present → pillar = None (excluded from composite,
   composite-level renormalisation handles the rest, same as V1).

3. **Pillar-level renormalisation kept.** When a pillar is fully absent
   (all components missing), it's dropped from the composite and the other
   pillars' weights are renormalised to sum to 1.0 — exactly as V1.

The recompute_all batch is called at the end of every successful scan run
(see scan_runner.run_tracked_scan) and after warmup_fundamentals — both
non-fatal so a score crash doesn't take down the upstream pipeline.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators.adx import adx as adx_indicator
from app.indicators.bb import bollinger
from app.indicators.macd import macd as macd_indicator
from app.indicators.rsi import rsi as rsi_indicator
from app.indicators.ema import ema as ema_indicator
from app.models import OhlcvDaily, Stock, StockScore
from app.services import sector_stats_service, stock_fundamentals_service, stock_news_service
from app.services.news_sentiment import classify_title
from app.services.sector_stats_service import SectorStatsBundle
from app.services.stock_fundamentals_service import (
    Fundamentals,
    MicroData,
)


# ---------------------------------------------------------------------------
# Pillar weights (composite-level) and risk tier set.
# ---------------------------------------------------------------------------

# V3.2 6-pillar framework: Quality has been split into Profitability
# (magnitude — ROE/ROA/margins) and Sustainability (durability — debt,
# liquidity, cash quality, earnings stability, dividend safety). Pesi
# riequilibrati sopra il 100% per dare più voce al "regge nel tempo?":
#   - Profitability: 0.15 (era 0.25 fuso con Sustainability)
#   - Sustainability: 0.15 (nuovo pilastro durability)
#   - Growth: 0.23 (era 0.25, lieve sgonfiamento per fare spazio)
#   - Value: 0.13 (era 0.15)
#   - Momentum: 0.20 (invariato)
#   - Sentiment: 0.14 (era 0.15)
# Total = 1.00.
PILLAR_WEIGHTS: dict[str, float] = {
    "profitability": 0.15,
    "sustainability": 0.15,
    "growth": 0.23,
    "value": 0.13,
    "momentum": 0.20,
    "sentiment": 0.14,
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


# ---------------------------------------------------------------------------
# Profitability pillar (V3.2 - was the magnitude side of Quality).
# ---------------------------------------------------------------------------

def _profitability(
    stock: Stock,
    micro: MicroData | None,
    sector_stats: SectorStatsBundle | None = None,
) -> tuple[float | None, float, dict]:
    """Profitability pillar - sector-aware blended scoring of return /
    margin metrics. Captures whether this is a money-making business
    in absolute terms AND vs its peers. Magnitude only - durability
    is in the sibling Sustainability pillar.

    Components (weights add to 1.0):
      - ROE                       (0.22)  HIB blend abs full@20%/half@10%/zero@0%, rel +5pp vs sector
      - ROA                       (0.15)  HIB blend abs full@10%/half@5%/zero@0%, rel +2.5pp
      - Profit margin             (0.20)  HIB blend abs full@20%/half@10%/zero@0%, rel +5pp
      - Operating margin          (0.15)  HIB blend abs full@20%/half@10%/zero@0%, rel +5pp
      - Gross margin              (0.13)  HIB blend abs full@50%/half@30%/zero@10%, rel +10pp
      - Insider holdings          (0.07)  HIB absolute (no peer aggregate)
      - Institutional holdings    (0.08)  HIB absolute (no peer aggregate)
    """
    if micro is None:
        return None, 100.0, {}

    components: list[_Component] = []
    sec = stock.sector

    def _med(field: str) -> float | None:
        return _resolve_med(sector_stats, sec, field)

    components.append(_Component(
        "roe", micro.return_on_equity,
        _blended_hib(micro.return_on_equity, _med("roe_median"),
                     abs_full=0.20, abs_half=0.10, abs_zero=0.0,
                     rel_full_pp=0.05),
        0.26,  # QW1: rebalanced after moving ownership out (0.22→0.26)
        sector_median=_med("roe_median"),
    ))
    components.append(_Component(
        "roa", micro.return_on_assets,
        _blended_hib(micro.return_on_assets, _med("roa_median"),
                     abs_full=0.10, abs_half=0.05, abs_zero=0.0,
                     rel_full_pp=0.025),
        0.18,  # QW1: rebalanced (roa 0.15→0.18)
        sector_median=_med("roa_median"),
    ))
    components.append(_Component(
        "profit_margin", micro.profit_margins,
        _blended_hib(micro.profit_margins, _med("profit_margin_median"),
                     abs_full=0.20, abs_half=0.10, abs_zero=0.0,
                     rel_full_pp=0.05),
        0.24,  # QW1: rebalanced (profit_margin 0.20→0.24)
        sector_median=_med("profit_margin_median"),
    ))
    components.append(_Component(
        "operating_margin", micro.operating_margins,
        _blended_hib(micro.operating_margins, _med("operating_margin_median"),
                     abs_full=0.20, abs_half=0.10, abs_zero=0.0,
                     rel_full_pp=0.05),
        0.18,  # QW1: rebalanced (operating_margin 0.15→0.18)
        sector_median=_med("operating_margin_median"),
    ))
    components.append(_Component(
        "gross_margin", micro.gross_margins,
        _blended_hib(micro.gross_margins, _med("gross_margin_median"),
                     abs_full=0.50, abs_half=0.30, abs_zero=0.10,
                     rel_full_pp=0.10),
        0.14,  # QW1: rebalanced (gross_margin 0.13→0.14); sum=1.00
        sector_median=_med("gross_margin_median"),
    ))
    # QW1: ownership is NOT profitability — insider/institutional holdings
    # are a positioning/sentiment signal that was contaminating the
    # economic meaning of this pillar and inflating its correlation with
    # Size/Sentiment. Kept at weight 0.0 (still shown in the breakdown as
    # informational, contributes nothing to the pillar score). A future
    # Medium refactor can promote them to a separate "Positioning"
    # micro-factor with its own (small) composite weight.
    components.append(_Component(
        "insider_holdings", micro.held_percent_insiders,
        _ramp3(micro.held_percent_insiders, full=0.10, half=0.03, zero=0.0)
        if _is_finite(micro.held_percent_insiders) else None,
        0.0,
    ))
    components.append(_Component(
        "institutional_holdings", micro.held_percent_institutions,
        _ramp3(micro.held_percent_institutions, full=0.70, half=0.40, zero=0.10)
        if _is_finite(micro.held_percent_institutions) else None,
        0.0,
    ))

    return _aggregate(components)


# ---------------------------------------------------------------------------
# Sustainability pillar (V3.2 - durability of the business).
# ---------------------------------------------------------------------------

def _sustainability(
    stock: Stock,
    fundamentals,
    sector_stats: SectorStatsBundle | None = None,
) -> tuple[float | None, float, dict]:
    """Sustainability pillar - answers whether this business will keep
    working over time.

    Combines balance-sheet solidity (D/E, liquidity ratios) with
    cash-flow quality (FCF positive, FCF/Net-Income ratio), earnings
    stability over time, margin durability, dividend safety, and
    Yahoo overall_risk.

    Components (weights add to 1.0):
      - Debt / Equity             (0.13)  LIB blend abs full@<=50/half@100/zero@200, rel -50pp
      - Current ratio             (0.10)  HIB blend abs full@2/half@1/zero@0.7, rel +0.5
      - Quick ratio               (0.08)  HIB blend abs full@1.5/half@1/zero@0.5, rel +0.5
      - FCF positive              (0.15)  binary
      - FCF / Net Income          (0.12)  HIB abs full@1.0/half@0.5/zero@0.0
      - Earnings stability 5y     (0.10)  inverse coefficient of variation of net_income
      - Margin trend 3y           (0.10)  signed slope of profit_margins
      - Dividend coverage         (0.10)  EPS / DPS - score=None when no dividend
      - Payout ratio sanity       (0.07)  healthy 30-60% band
      - Yahoo overall_risk        (0.05)  1 (best) -> 10 (worst)
    """
    if fundamentals is None:
        return None, 100.0, {}
    micro = fundamentals.micro
    if micro is None:
        return None, 100.0, {}

    components: list[_Component] = []
    sec = stock.sector

    def _med(field: str) -> float | None:
        return _resolve_med(sector_stats, sec, field)

    components.append(_Component(
        "debt_equity", micro.debt_to_equity,
        _blended_lib(micro.debt_to_equity, _med("debt_equity_median"),
                     abs_full=50.0, abs_half=100.0, abs_zero=200.0,
                     rel_full_pp=-50.0),
        0.13,
        sector_median=_med("debt_equity_median"),
    ))
    components.append(_Component(
        "current_ratio", micro.current_ratio,
        _blended_hib(micro.current_ratio, _med("current_ratio_median"),
                     abs_full=2.0, abs_half=1.0, abs_zero=0.7,
                     rel_full_pp=0.5),
        0.10,
        sector_median=_med("current_ratio_median"),
    ))
    components.append(_Component(
        "quick_ratio", micro.quick_ratio,
        _blended_hib(micro.quick_ratio, _med("quick_ratio_median"),
                     abs_full=1.5, abs_half=1.0, abs_zero=0.5,
                     rel_full_pp=0.5),
        0.08,
        sector_median=_med("quick_ratio_median"),
    ))

    fcf = micro.free_cashflow
    components.append(_Component(
        "fcf", fcf,
        (100.0 if fcf > 0 else 0.0) if _is_finite(fcf) else None,
        0.15,
    ))

    fcf_to_ni = _fcf_to_ni_ratio(fundamentals)
    components.append(_Component(
        "fcf_to_ni", fcf_to_ni,
        _ramp3(fcf_to_ni, full=1.0, half=0.5, zero=0.0)
        if fcf_to_ni is not None else None,
        0.12,
        sector_median=_med("fcf_to_ni_median"),
    ))

    earn_stab = _earnings_stability_5y(fundamentals)
    components.append(_Component(
        "earnings_stability", earn_stab,
        _ramp3(earn_stab, full=0.85, half=0.5, zero=0.15)
        if earn_stab is not None else None,
        0.10,
    ))

    margin_slope = _margin_trend_3y(fundamentals)
    components.append(_Component(
        "margin_trend", margin_slope,
        _ramp3(margin_slope, full=0.02, half=0.0, zero=-0.02)
        if margin_slope is not None else None,
        0.10,
    ))

    div_cov = _dividend_coverage(micro)
    components.append(_Component(
        "dividend_coverage", div_cov,
        _ramp3(div_cov, full=3.0, half=1.5, zero=1.0)
        if div_cov is not None else None,
        0.10,
        sector_median=_med("dividend_coverage_median"),
    ))

    pr = micro.payout_ratio
    pr_score = None
    has_dividend = (
        _is_finite(micro.dividend_yield) and micro.dividend_yield is not None
        and micro.dividend_yield > 0
    )
    if _is_finite(pr) and pr is not None and has_dividend:
        if pr <= 0:
            pr_score = 0.0
        elif pr <= 0.30:
            pr_score = 70.0
        elif pr <= 0.60:
            pr_score = 100.0
        elif pr <= 1.0:
            pr_score = max(0.0, 100.0 * (1.0 - (pr - 0.60) / 0.40))
        else:
            pr_score = 0.0
    components.append(_Component("payout_ratio", pr if has_dividend else None, pr_score, 0.07))

    components.append(_Component(
        "overall_risk", micro.overall_risk,
        _ramp(micro.overall_risk, full=1.0, zero=10.0) if _is_finite(micro.overall_risk) else None,
        0.05,
    ))

    return _aggregate(components)


# ---------------------------------------------------------------------------
# Sustainability lane helpers (V3.2 new metrics).
# ---------------------------------------------------------------------------

def _fcf_to_ni_ratio(fundamentals) -> float | None:
    """FCF / Net Income ratio. >1 means earnings backed by cash, <1
    means accruals, <0 means cash burn despite reported profit.

    Net income source priority:
      1. micro.net_income_to_common (Yahoo info dict, TTM)
      2. Latest fundamentals.annual entry net_income
      3. Sum of latest 4 quarterlies (TTM rebuild)

    Returns None when no net_income source yields a finite, positive
    value (ratio undefined or meaningless), or when FCF is unavailable.
    """
    micro = fundamentals.micro if fundamentals is not None else None
    if micro is None:
        return None
    fcf = micro.free_cashflow
    if not _is_finite(fcf):
        return None
    ni: float | None = None
    candidate = getattr(micro, "net_income_to_common", None)
    if _is_finite(candidate) and candidate is not None and float(candidate) > 0:
        ni = float(candidate)
    else:
        annual = getattr(fundamentals, "annual", None) or []
        for ap in reversed(annual):
            v = getattr(ap, "net_income", None)
            if _is_finite(v) and v is not None and float(v) > 0:
                ni = float(v)
                break
    if ni is None or ni <= 0:
        return None
    return float(fcf) / ni


def _earnings_stability_5y(fundamentals) -> float | None:
    """Inverse coefficient of variation of net_income over up to 5
    annual reports. Returns 1 - CV clipped to [0, 1] so the consumer
    ramp gets a higher-is-better signal.

    Returns None with fewer than 3 data points or non-positive mean.
    """
    annual = getattr(fundamentals, "annual", None) or []
    nis = [
        float(a.net_income) for a in annual
        if getattr(a, "net_income", None) is not None
        and _is_finite(a.net_income)
    ][-5:]
    if len(nis) < 3:
        return None
    import statistics
    # Robustness vs M&A one-offs (the Omnicom/Interpublic FY25 case):
    # a single year of GAAP net income wrecked by merger/restructuring
    # charges (e.g. +1.48B → −55M) blows the raw CV up and zeroes this
    # lane even for an operationally healthy company. With ≥4 reports
    # we drop the SINGLE point furthest from the median (a standard
    # trimmed estimator) and compute CV on the rest — ≥3 points always
    # remain. A *persistent* GAAP shortfall (multiple bad years) still
    # drags the lane, which is the correct earnings-quality penalty;
    # only the lone transient shock is neutralised.
    if len(nis) >= 4:
        med = statistics.median(nis)
        worst = max(range(len(nis)), key=lambda i: abs(nis[i] - med))
        nis = [v for i, v in enumerate(nis) if i != worst]
    mean = sum(nis) / len(nis)
    if mean <= 0:
        return None
    try:
        stdev = statistics.stdev(nis)
    except statistics.StatisticsError:
        return None
    cv = stdev / mean
    return max(0.0, 1.0 - cv)


def _margin_trend_3y(fundamentals) -> float | None:
    """Robust slope of profit_margin over the last (up to) 5 annual
    reports, in fraction-per-year units (+0.02 ≈ +2pp/year).

    Uses the Theil–Sen estimator (median of all pairwise slopes)
    instead of OLS. Rationale: a single M&A/impairment year (the
    Omnicom FY25 GAAP loss) drags an OLS line through 3 points to a
    sharply negative slope and unfairly punishes the quality pillar.
    Theil–Sen ignores up to ~29% of outlying points by construction,
    so one transient shock can't flip the trend — while a *persistent*
    margin decline (the majority of pairwise slopes negative) still
    registers correctly. Widened from 3→5 years so the median has
    enough pairs to be meaningful. Returns None below 3 valid points.
    """
    annual = getattr(fundamentals, "annual", None) or []
    margins: list[float] = []
    for a in annual[-5:]:
        rev = getattr(a, "revenue", None)
        ni = getattr(a, "net_income", None)
        if not _is_finite(rev) or not _is_finite(ni) or rev is None or float(rev) <= 0:
            continue
        margins.append(float(ni) / float(rev))
    if len(margins) < 3:
        return None
    import statistics
    slopes = [
        (margins[j] - margins[i]) / (j - i)
        for i in range(len(margins))
        for j in range(i + 1, len(margins))
    ]
    if not slopes:
        return 0.0
    return statistics.median(slopes)


def _dividend_coverage(micro) -> float | None:
    """EPS (TTM) / annual dividend per share. >=3x is very safe,
    1-1.5x is tight, <1x means paying out of debt or reserves.
    Returns None for non-dividend-paying stocks (the lane drops out).
    """
    eps = getattr(micro, "eps_trailing", None)
    div_rate = getattr(micro, "dividend_rate", None)
    if not _is_finite(eps) or not _is_finite(div_rate):
        return None
    if div_rate is None or float(div_rate) <= 0:
        return None
    if eps is None or float(eps) <= 0:
        return 0.0
    return float(eps) / float(div_rate)




# ---------------------------------------------------------------------------
# Back-compat shim: _quality() returns a merged breakdown so V3.1-era
# callers (and the existing test suite) keep working without changes.
# New code should call _profitability and _sustainability directly.
# ---------------------------------------------------------------------------

def _quality(
    stock: Stock,
    micro: MicroData | None,
    sector_stats: SectorStatsBundle | None = None,
) -> tuple[float | None, float, dict]:
    """V3.1 back-compat alias. Computes profitability and sustainability,
    merges their breakdowns, and returns avg(p, s) as the "quality" score.

    Sustainability normally needs a Fundamentals wrapper (for the
    earnings-stability and margin-trend lanes that read annual reports).
    When the caller only has a MicroData (e.g. unit tests), we wrap it
    in a minimal stand-in with an empty annual list so the lane simply
    drops out of the aggregate.
    """
    from dataclasses import dataclass, field as _field

    @dataclass
    class _FundShim:
        micro: MicroData | None
        annual: list = _field(default_factory=list)
        quarterly: list = _field(default_factory=list)
        earnings: list = _field(default_factory=list)

    fund = _FundShim(micro=micro) if micro is not None else None
    p_score, _, p_br = _profitability(stock, micro, sector_stats)
    s_score, _, s_br = _sustainability(stock, fund, sector_stats)

    merged: dict[str, Any] = {}
    merged.update(p_br)
    merged.update(s_br)

    if p_score is None and s_score is None:
        return None, 100.0, merged
    if p_score is None:
        return s_score, 100.0, merged
    if s_score is None:
        return p_score, 100.0, merged
    return (p_score + s_score) / 2.0, 100.0, merged

# ---------------------------------------------------------------------------
# Growth pillar.
# ---------------------------------------------------------------------------

def _growth(stock: Stock, fundamentals: Fundamentals | None, sector_stats: SectorStatsBundle | None = None) -> tuple[float | None, float, dict]:
    """Growth pillar - sector-aware blended scoring.

    YoY revenue / earnings growth + qoq earnings now blend each
    stock's value with its sector's median peer growth (50/50). A
    12% revenue grower in semis (sector median ~22%) is below par;
    the same 12% in utilities (sector median ~3%) is excellent.

    Components (rebalanced V3.6 — added Rev QoQ + 5y CAGRs for rev/eps,
    all sector-aware where a peer median exists; the old mislabeled
    "3y" revenue CAGR is replaced by the cleaner 5y one computed in
    `_fill_growth_fallbacks`):
      - Revenue growth (YoY)        (0.18)  HIB blend
      - Earnings growth (YoY)       (0.18)  HIB blend
      - Quarterly earnings growth   (0.10)  HIB blend
      - Quarterly revenue growth    (0.08)  HIB blend  [NEW]
      - EPS forward vs trailing     (0.08)  HIB absolute
      - Earnings beats (last 4 q)   (0.12)  HIB absolute
      - Revenue growth (5Y CAGR)    (0.13)  HIB blend  [was 3y abs]
      - Earnings growth (5Y CAGR)   (0.13)  HIB blend  [NEW]
    """
    if fundamentals is None:
        return None, 100.0, {}
    micro = fundamentals.micro
    sec = stock.sector

    def _med(field):
        return _resolve_med(sector_stats, sec, field)

    components: list[_Component] = []

    # --- Revenue & earnings YoY (sector-aware blend) ----------------------
    rg = micro.revenue_growth if micro else None
    components.append(_Component(
        "revenue_growth", rg,
        _blended_hib(rg, _med("revenue_growth_median"),
                     abs_full=0.20, abs_half=0.0, abs_zero=-0.10,
                     rel_full_pp=0.05),
        0.18,
    sector_median=_med("revenue_growth_median"),
    ))
    eg = micro.earnings_growth if micro else None
    components.append(_Component(
        "earnings_growth", eg,
        _blended_hib(eg, _med("earnings_growth_median"),
                     abs_full=0.20, abs_half=0.0, abs_zero=-0.10,
                     rel_full_pp=0.05),
        0.18,
    sector_median=_med("earnings_growth_median"),
    ))
    qeg = micro.earnings_quarterly_growth if micro else None
    components.append(_Component(
        "qoq_earnings_growth", qeg,
        _blended_hib(qeg, _med("earnings_quarterly_growth_median"),
                     abs_full=0.25, abs_half=0.0, abs_zero=-0.15,
                     rel_full_pp=0.10),
        0.10,
    sector_median=_med("earnings_quarterly_growth_median"),
    ))
    qrg = micro.revenue_quarterly_growth if micro else None
    components.append(_Component(
        "qoq_revenue_growth", qrg,
        _blended_hib(qrg, _med("revenue_quarterly_growth_median"),
                     abs_full=0.10, abs_half=0.0, abs_zero=-0.06,
                     rel_full_pp=0.05),
        0.08,
    sector_median=_med("revenue_quarterly_growth_median"),
    ))

    # --- Forward EPS vs trailing EPS (no sector aggregate) ---------------
    eps_t = micro.eps_trailing if micro else None
    eps_f = micro.eps_forward if micro else None
    fwd_growth = None
    if _is_finite(eps_t) and _is_finite(eps_f) and eps_t and eps_t > 0:
        fwd_growth = (float(eps_f) - float(eps_t)) / float(eps_t)
    components.append(_Component(
        "eps_forward_growth", fwd_growth,
        _ramp3(fwd_growth, full=0.20, half=0.0, zero=-0.10) if fwd_growth is not None else None,
        0.08,
    ))

    # --- Earnings-beats history (no sector aggregate) --------------------
    earnings = fundamentals.earnings or []
    last4 = [e for e in earnings if e.eps_reported is not None and e.eps_estimate is not None][-4:]
    if last4:
        beats = sum(1 for e in last4 if e.eps_reported > e.eps_estimate)
        beat_score = _ramp3(float(beats), full=4.0, half=2.0, zero=0.0)
        components.append(_Component("earnings_beats", beats, beat_score, 0.12))
    else:
        components.append(_Component("earnings_beats", None, None, 0.12))

    # --- Multi-year CAGRs (sector-aware) --------------------------------
    # Replaces the old inline "revenue_cagr_3y" (which was actually a
    # 2-year exponent off 3 annual points). Now reads the cleanly
    # computed 5y CAGRs from `_fill_growth_fallbacks` for BOTH revenue
    # and earnings, scored relative to the sector like the YoY metrics.
    r5 = micro.revenue_growth_5y if micro else None
    components.append(_Component(
        "revenue_growth_5y", r5,
        _blended_hib(r5, _med("revenue_growth_5y_median"),
                     abs_full=0.15, abs_half=0.05, abs_zero=-0.05,
                     rel_full_pp=0.04),
        0.13,
    sector_median=_med("revenue_growth_5y_median"),
    ))
    e5 = micro.earnings_growth_5y if micro else None
    components.append(_Component(
        "earnings_growth_5y", e5,
        _blended_hib(e5, _med("earnings_growth_5y_median"),
                     abs_full=0.15, abs_half=0.05, abs_zero=-0.05,
                     rel_full_pp=0.04),
        0.13,
    sector_median=_med("earnings_growth_5y_median"),
    ))

    return _aggregate(components)

# ---------------------------------------------------------------------------
# Value pillar.
# ---------------------------------------------------------------------------

def _value(
    stock: Stock,
    micro: MicroData | None,
    last_close: float | None,
    sector_stats: SectorStatsBundle | None = None,
) -> tuple[float | None, float, dict]:
    """Value pillar - sector-aware blended scoring.

    Each multiple is blended 50/50 between absolute (canonical
    full/half/zero ramp) and sector-relative scoring (ratio of stock
    multiple / sector median). A P/E of 28 in tech (sector median ~28)
    sits at par; the same 28 in utilities (sector ~22) is meaningfully
    expensive vs peers.

    Components (weights add to 1.0):
      - P/E (TTM)                   (0.22)  LIB-multiple blend, abs full@22/half@33/zero@44
      - Forward P/E                 (0.10)  LIB-multiple blend, same shape
      - PEG                         (0.18)  LIB-multiple blend, abs full@1.0/half@2.0/zero@3.0
      - P/B                         (0.10)  LIB-multiple blend, abs full@3.0/half@4.5/zero@6.0
      - P/S                         (0.08)  LIB-multiple blend, abs full@2.0/half@5.0/zero@10.0
      - EV / EBITDA                 (0.10)  LIB-multiple blend, abs full@8/half@14/zero@25
      - EV / Revenue                (0.05)  LIB-multiple blend, abs full@2/half@5/zero@10
      - Dividend yield              (0.10)  HIB blend, abs full@>=3%/zero@0%, rel +1pp vs sector
      - Payout ratio sanity         (0.07)  absolute (no sector aggregate; healthy band)
    """
    if micro is None:
        return None, 100.0, {}

    sec = stock.sector

    def _med(field):
        return _resolve_med(sector_stats, sec, field)

    components: list[_Component] = []

    # --- Trailing P/E (sector-aware blend) -------------------------------
    components.append(_Component(
        "pe", micro.trailing_pe,
        _blended_lib_multiple(micro.trailing_pe, _med("pe_median"),
                              abs_full=22.0, abs_half=33.0, abs_zero=44.0),
        0.25,  # QW1: +0.03 (absorbs part of removed payout double-count)
    sector_median=_med("pe_median"),
    ))

    # --- Forward P/E (sector-aware blend) --------------------------------
    components.append(_Component(
        "forward_pe", micro.forward_pe,
        _blended_lib_multiple(micro.forward_pe, _med("forward_pe_median"),
                              abs_full=22.0, abs_half=33.0, abs_zero=44.0),
        0.10,
    sector_median=_med("forward_pe_median"),
    ))

    # --- PEG (prefer trailing if available; sector-aware) ----------------
    peg = micro.trailing_peg_ratio if _is_finite(micro.trailing_peg_ratio) else micro.peg_ratio
    components.append(_Component(
        "peg", peg,
        _blended_lib_multiple(peg, _med("peg_median"),
                              abs_full=1.0, abs_half=2.0, abs_zero=3.0),
        0.21,  # QW1: +0.03 (absorbs part of removed payout double-count)
    sector_median=_med("peg_median"),
    ))

    # --- P/B (sector-aware blend) ----------------------------------------
    components.append(_Component(
        "pb", micro.price_to_book,
        _blended_lib_multiple(micro.price_to_book, _med("pb_median"),
                              abs_full=3.0, abs_half=4.5, abs_zero=6.0),
        0.10,
    sector_median=_med("pb_median"),
    ))

    # --- P/S (sector-aware blend) ----------------------------------------
    components.append(_Component(
        "ps", micro.price_to_sales,
        _blended_lib_multiple(micro.price_to_sales, _med("ps_median"),
                              abs_full=2.0, abs_half=5.0, abs_zero=10.0),
        0.08,
    sector_median=_med("ps_median"),
    ))

    # --- EV/EBITDA (sector-aware blend) ----------------------------------
    components.append(_Component(
        "ev_ebitda", micro.enterprise_to_ebitda,
        _blended_lib_multiple(micro.enterprise_to_ebitda, _med("ev_ebitda_median"),
                              abs_full=8.0, abs_half=14.0, abs_zero=25.0),
        0.11,  # QW1: +0.01 (absorbs part of removed payout double-count)
    sector_median=_med("ev_ebitda_median"),
    ))

    # --- EV/Revenue (sector-aware blend) ---------------------------------
    components.append(_Component(
        "ev_revenue", micro.enterprise_to_revenue,
        _blended_lib_multiple(micro.enterprise_to_revenue, _med("ev_revenue_median"),
                              abs_full=2.0, abs_half=5.0, abs_zero=10.0),
        0.05,
    sector_median=_med("ev_revenue_median"),
    ))

    # --- Dividend yield (sector-aware HIB blend) -------------------------
    # yfinance is inconsistent: <1 -> fraction, >=1 -> percent.
    dy_raw = micro.dividend_yield
    dy_pct = None
    if _is_finite(dy_raw) and dy_raw is not None and dy_raw >= 0:
        dy_pct = dy_raw if dy_raw > 1 else dy_raw * 100.0
    components.append(_Component(
        "dividend_yield", dy_pct,
        _blended_hib(dy_pct, _med("dividend_yield_median"),
                     abs_full=3.0, abs_half=1.5, abs_zero=0.0,
                     rel_full_pp=1.0) if dy_pct is not None else None,
        0.10,
    sector_median=_med("dividend_yield_median"),
    ))

    # QW1: payout-ratio sanity REMOVED from Value — it was double-counted
    # (identical lane already weighted 0.07 in _sustainability). Keeping it
    # in both pillars put implicit ~+0.07 leverage on a single low-IC
    # dividend-safety signal. The freed 0.07 was redistributed to the core
    # value multiples (P/E +0.03, PEG +0.03, EV/EBITDA +0.01) so the pillar
    # still sums to 1.0. Dividend *yield* (a genuine value signal) stays;
    # only the duplicated payout *sanity* lane is dropped here.

    return _aggregate(components)

# ---------------------------------------------------------------------------
# Momentum pillar.
# ---------------------------------------------------------------------------

def _momentum(
    stock: Stock,
    micro: MicroData | None,
    closes: pd.Series | None,
    ohlcv_df: pd.DataFrame | None = None,
) -> tuple[float | None, float, dict]:
    """Components (weights sum to 1.0):

      - 52-week change            (0.18)  full @ ≥+50%, half @ 0%, zero @ -30%
      - 30-day momentum           (0.14)  full @ +10%, half @ 0%, zero @ -10%
      - 90-day momentum           (0.10)  full @ +20%, half @ 0%, zero @ -15%
      - Trend: EMA20 > EMA50 > EMA200  (0.12)  staircase (1.0/0.66/0.33/0.0)
      - Price vs EMA200           (0.10)  full @ +15%, half @ 0%, zero @ -15%
      - RSI(14)                   (0.08)  oversold > neutral > overbought
      - MACD bullishness          (0.10)  binary line>signal AND hist>0
      - Bollinger position        (0.06)  centered = best, near upper/lower = worse
      - ADX trend strength        (0.06)  full @ ≥30, half @ 20, zero @ <15
      - Relative strength vs S&P  (0.06)  fifty_two_week_change − sp500_…
    """
    closes_present = closes is not None and len(closes) > 0
    components: list[_Component] = []

    # --- 52-week change (prefer micro field; fall back to bars) ----------
    chg_52w: float | None = None
    if micro is not None and _is_finite(micro.fifty_two_week_change):
        chg_52w = float(micro.fifty_two_week_change)
    elif closes_present and closes is not None and len(closes) >= 252:
        ref = float(closes.iloc[-252])
        if ref > 0:
            chg_52w = (float(closes.iloc[-1]) - ref) / ref
    components.append(_Component(
        "change_52w", chg_52w,
        _ramp3(chg_52w, full=0.50, half=0.0, zero=-0.30) if chg_52w is not None else None,
        0.18,
    ))

    # --- 30-day momentum --------------------------------------------------
    mom30: float | None = None
    if closes_present and closes is not None and len(closes) >= 22:
        ref = float(closes.iloc[-22])
        if ref > 0:
            mom30 = (float(closes.iloc[-1]) - ref) / ref
    components.append(_Component(
        "momentum_30d", mom30,
        _ramp3(mom30, full=0.10, half=0.0, zero=-0.10) if mom30 is not None else None,
        0.14,
    ))

    # --- 90-day momentum --------------------------------------------------
    mom90: float | None = None
    if closes_present and closes is not None and len(closes) >= 65:
        ref = float(closes.iloc[-65])
        if ref > 0:
            mom90 = (float(closes.iloc[-1]) - ref) / ref
    components.append(_Component(
        "momentum_90d", mom90,
        _ramp3(mom90, full=0.20, half=0.0, zero=-0.15) if mom90 is not None else None,
        0.10,
    ))

    # --- Trend stacking: EMA20 > EMA50 > EMA200 --------------------------
    trend_score: float | None = None
    ema20_v = ema50_v = ema200_v = None
    last_close = float(closes.iloc[-1]) if closes_present and closes is not None else None
    if closes_present and closes is not None and len(closes) >= 200:
        try:
            ema20_v = float(ema_indicator(closes, 20).iloc[-1])
            ema50_v = float(ema_indicator(closes, 50).iloc[-1])
            ema200_v = float(ema_indicator(closes, 200).iloc[-1])
            if all(pd.notna(v) for v in (ema20_v, ema50_v, ema200_v)) and last_close is not None:
                # Score 0..3 of "stacked correctly" rules.
                rules = [
                    last_close > ema20_v,
                    ema20_v > ema50_v,
                    ema50_v > ema200_v,
                ]
                trend_score = 100.0 * sum(1 for r in rules if r) / 3.0
        except Exception:  # noqa: BLE001
            trend_score = None
    components.append(_Component(
        "trend_stack",
        {"close": _safe_round(last_close or 0.0, 2),
         "ema20": _safe_round(ema20_v or 0.0, 2),
         "ema50": _safe_round(ema50_v or 0.0, 2),
         "ema200": _safe_round(ema200_v or 0.0, 2)} if trend_score is not None else None,
        trend_score,
        0.12,
    ))

    # --- Price vs EMA200 -------------------------------------------------
    px_vs_ema200: float | None = None
    if ema200_v is not None and last_close is not None and pd.notna(ema200_v) and ema200_v > 0:
        px_vs_ema200 = (last_close - ema200_v) / ema200_v
    components.append(_Component(
        "price_vs_ema200", px_vs_ema200,
        _ramp3(px_vs_ema200, full=0.15, half=0.0, zero=-0.15) if px_vs_ema200 is not None else None,
        0.10,
    ))

    # --- RSI(14) ---------------------------------------------------------
    rsi_val: float | None = None
    if closes_present and closes is not None and len(closes) >= 15:
        try:
            last_rsi = rsi_indicator(closes, 14).iloc[-1]
            if pd.notna(last_rsi):
                rsi_val = float(last_rsi)
        except Exception:  # noqa: BLE001
            rsi_val = None
    rsi_score: float | None = None
    if rsi_val is not None:
        # Slightly oversold (30-45) is the sweet spot — bounce candidate
        # without being broken. Overbought (>70) penalised; very oversold
        # (<25) gets a smaller reward (could still keep falling).
        if rsi_val < 25:
            rsi_score = 70.0
        elif rsi_val < 30:
            rsi_score = 80.0
        elif rsi_val < 45:
            rsi_score = 75.0
        elif rsi_val <= 60:
            rsi_score = 60.0
        elif rsi_val <= 70:
            rsi_score = 40.0
        else:
            rsi_score = 20.0
    components.append(_Component("rsi", rsi_val, rsi_score, 0.08))

    # --- MACD bullishness ------------------------------------------------
    macd_score: float | None = None
    macd_state: str | None = None
    macd_hist: float | None = None
    if closes_present and closes is not None and len(closes) >= 35:
        try:
            line, sig, hist = macd_indicator(closes, fast=12, slow=26, signal=9)
            line_v = float(line.iloc[-1]) if pd.notna(line.iloc[-1]) else None
            sig_v = float(sig.iloc[-1]) if pd.notna(sig.iloc[-1]) else None
            hist_v = float(hist.iloc[-1]) if pd.notna(hist.iloc[-1]) else None
            if line_v is not None and sig_v is not None and hist_v is not None:
                macd_hist = hist_v
                if line_v > sig_v and hist_v > 0:
                    macd_score = 100.0
                    macd_state = "bullish"
                elif line_v > sig_v or hist_v > 0:
                    macd_score = 50.0
                    macd_state = "mixed"
                else:
                    macd_score = 0.0
                    macd_state = "bearish_or_flat"
        except Exception:  # noqa: BLE001
            macd_score = None
    components.append(_Component(
        "macd",
        {"hist": _safe_round(macd_hist, 4) if macd_hist is not None else None, "state": macd_state}
        if macd_state is not None else None,
        macd_score,
        0.10,
    ))

    # --- Bollinger Band position ----------------------------------------
    bb_score: float | None = None
    bb_pct_b: float | None = None
    if closes_present and closes is not None and len(closes) >= 20:
        try:
            up, mid, lo = bollinger(closes, period=20, k=2.0)
            up_v = float(up.iloc[-1]) if pd.notna(up.iloc[-1]) else None
            lo_v = float(lo.iloc[-1]) if pd.notna(lo.iloc[-1]) else None
            if up_v is not None and lo_v is not None and up_v > lo_v and last_close is not None:
                # %B: 0 = lower band, 1 = upper band. Reward ~0.4-0.7
                # (rising-but-not-overextended), penalise ≤0.1 / ≥0.95.
                pb = (last_close - lo_v) / (up_v - lo_v)
                bb_pct_b = pb
                if 0.4 <= pb <= 0.7:
                    bb_score = 100.0
                elif 0.25 <= pb < 0.4:
                    bb_score = 80.0
                elif 0.7 < pb <= 0.85:
                    bb_score = 70.0
                elif 0.1 <= pb < 0.25:
                    bb_score = 50.0
                elif 0.85 < pb <= 0.95:
                    bb_score = 40.0
                else:
                    bb_score = 20.0  # touching either band
        except Exception:  # noqa: BLE001
            bb_score = None
    components.append(_Component("bb_position", bb_pct_b, bb_score, 0.06))

    # --- ADX (trend strength) -------------------------------------------
    adx_val: float | None = None
    if ohlcv_df is not None and len(ohlcv_df) >= 30:
        try:
            adx_series, _, _ = adx_indicator(ohlcv_df, period=14)
            last = adx_series.iloc[-1]
            if pd.notna(last):
                adx_val = float(last)
        except Exception:  # noqa: BLE001
            adx_val = None
    components.append(_Component(
        "adx", adx_val,
        _ramp3(adx_val, full=30.0, half=20.0, zero=15.0) if adx_val is not None else None,
        0.06,
    ))

    # --- Relative strength vs S&P 500 ------------------------------------
    # QW4: only meaningful for US names. Subtracting the S&P 500 12-month
    # return from a .MI / .L / .HK stock injects US market beta as fake
    # idiosyncratic alpha (wrong-benchmark error). Better "no signal"
    # (component neutralised → renormalised away) than a wrong one, until
    # a per-listing-market benchmark is wired (Medium follow-up).
    rel_strength: float | None = None
    if (
        stock.country == "US"
        and micro is not None
        and _is_finite(micro.fifty_two_week_change)
        and _is_finite(micro.sp500_fifty_two_week_change)
    ):
        rel_strength = float(micro.fifty_two_week_change) - float(
            micro.sp500_fifty_two_week_change
        )
    components.append(_Component(
        "relative_strength", rel_strength,
        _ramp3(rel_strength, full=0.20, half=0.0, zero=-0.20) if rel_strength is not None else None,
        0.06,
    ))

    return _aggregate(components)


# ---------------------------------------------------------------------------
# Sentiment pillar.
# ---------------------------------------------------------------------------

def _net_upgrades_90d(fundamentals: Fundamentals) -> int | None:
    """Count net upgrades − downgrades from analyst_actions over the last 90d."""
    actions = fundamentals.analyst_actions or []
    if not actions:
        return None
    today = datetime.now(UTC).date()
    net = 0
    seen = 0
    for a in actions:
        try:
            d = datetime.fromisoformat(a.date).date()
        except (TypeError, ValueError):
            continue
        if (today - d).days > 90:
            continue
        seen += 1
        code = (a.action or "").strip().lower()
        if code == "up":
            net += 1
        elif code == "down":
            net -= 1
    return net if seen > 0 else None


def _aggregate_news_sentiment(
    ticker: str,
    *,
    limit: int = 10,
) -> tuple[int | None, float | None]:
    """Return (count_recent, polarity_score_-100..+100) over the last `limit`
    cached headlines. None on cold cache or fetch failure.

    Polarity = (bullish - bearish) / total * 100, in [-100, 100].
    Headlines that already carry a server-side `sentiment` field (set by
    stock_news_service) reuse it; otherwise we re-classify on the fly via
    classify_title — defensive against older cached payloads.
    """
    try:
        items = stock_news_service.get_news(ticker, limit=limit)
    except Exception:  # noqa: BLE001
        return None, None
    if not items:
        return 0, None  # we know there are no headlines (cold cache or empty)

    bull = bear = neutral = 0
    for it in items[:limit]:
        # Prefer pre-computed sentiment in the cache; fall back to classifier.
        s = it.get("sentiment")
        if s not in ("bullish", "bearish", "neutral"):
            s = classify_title(it.get("title"))
        if s == "bullish":
            bull += 1
        elif s == "bearish":
            bear += 1
        else:
            neutral += 1
    total = bull + bear + neutral
    if total == 0:
        return 0, None
    polarity = 100.0 * (bull - bear) / total
    return total, polarity


def _sentiment(
    stock: Stock,
    fundamentals: Fundamentals | None,
    last_close: float | None,
    *,
    news_polarity: float | None,
    news_count: int | None,
) -> tuple[float | None, float, dict]:
    """Components:

      - Analyst price-target upside (0.30)  full @ +20%, half @ 0%, zero @ -10%
      - Analyst recommendation_mean (0.20)  yfinance: 1=buy → 5=sell
      - Net analyst upgrades 90d    (0.18)  full @ +3, half @ 0, zero @ -3
      - News volume (last 30d)      (0.07)  saturating at 20 articles
      - News polarity               (0.20)  bullish vs bearish headline mix
      - Short interest signal       (0.05)  inverse: short% high → low score
    """
    if fundamentals is None and news_polarity is None and news_count is None:
        # No fundamentals AND no news at all → nothing to score.
        return None, 100.0, {}

    components: list[_Component] = []
    micro = fundamentals.micro if fundamentals is not None else None

    # --- Price-target upside --------------------------------------------
    pt_mean = (
        fundamentals.price_target.mean
        if fundamentals is not None and fundamentals.price_target
        else None
    )
    upside: float | None = None
    if (
        _is_finite(pt_mean)
        and _is_finite(last_close)
        and last_close
        and last_close > 0
    ):
        upside = (float(pt_mean) - float(last_close)) / float(last_close)
    components.append(_Component(
        "price_target_upside", upside,
        _ramp3(upside, full=0.20, half=0.0, zero=-0.10) if upside is not None else None,
        0.10,  # QW2: 0.30→0.10 — low-IC, lagging, anchored, sell-side
               # optimism bias; also the main Sentiment↔Momentum crowding
               # channel (targets are anchored to price).
    ))

    # --- Analyst recommendation mean (1=strong buy ↔ 5=sell) --------------
    rec = micro.recommendation_mean if micro else None
    components.append(_Component(
        "recommendation_mean", rec,
        _ramp(rec, full=1.5, zero=4.0) if _is_finite(rec) else None,
        0.20,
    ))

    # --- Net upgrades − downgrades (90d) ---------------------------------
    net_up: int | None = None
    if fundamentals is not None:
        net_up = _net_upgrades_90d(fundamentals)
    components.append(_Component(
        "net_upgrades_90d", net_up,
        _ramp3(float(net_up), full=3.0, half=0.0, zero=-3.0) if net_up is not None else None,
        0.28,  # QW2: 0.18→0.28 — estimate-revision/upgrade flow is the
               # robust analyst signal (higher IC than target levels).
    ))

    # --- News volume (recent count) -------------------------------------
    components.append(_Component(
        "news_volume", news_count,
        _ramp(float(news_count), full=20.0, zero=0.0) if news_count is not None else None,
        0.07,
    ))

    # --- News polarity (bullish - bearish ratio of recent headlines) -----
    # polarity ∈ [-100, +100]; map +50 → full, 0 → half, -50 → zero.
    components.append(_Component(
        "news_polarity", news_polarity,
        _ramp3(news_polarity, full=50.0, half=0.0, zero=-50.0) if news_polarity is not None else None,
        0.20,
    ))

    # --- Short interest signal -------------------------------------------
    # short_percent_of_float (fraction): high short% → market is betting
    # against. Treat <2% as neutral, ≥10% as serious bearish, ≥20% as max.
    spf = micro.short_percent_of_float if micro else None
    spf_score: float | None = None
    if _is_finite(spf) and spf is not None and spf >= 0:
        # Lower-is-better ramp: 0% → full, 20% → zero, half at 5%.
        spf_score = _ramp3(spf, full=0.0, half=0.05, zero=0.20)
    components.append(_Component("short_percent_of_float", spf, spf_score, 0.15))  # QW2: 0.05→0.15 (robust, under-weighted anomaly)

    return _aggregate(components)


# ---------------------------------------------------------------------------
# Risk classification (richer signals than V1).
# ---------------------------------------------------------------------------

def _classify_risk(
    stock: Stock,
    micro: MicroData | None,
    volatility_90d: float | None,
) -> str:
    """Map (Beta, vol, sector, market_cap, leverage, drawdown) → tier.

    Each input contributes -1 / 0 / +1 votes; sum is thresholded.
      - Beta < 0.8 → conservative; > 1.3 → aggressive
      - 90d vol < 1.5%/day → conservative; > 3%/day → aggressive
      - Defensive sectors → conservative; cyclical → aggressive
      - Market cap > $200B → -1 (mega-cap stability)
      - Market cap < $2B   → +1 (small-cap volatility)
      - debt_to_equity > 200% (highly levered) → +1
      - Yahoo overall_risk score: 1-3 → -1, 8-10 → +1
    """
    score = 0
    inputs = 0

    beta = micro.beta if micro is not None else None
    if _is_finite(beta):
        inputs += 1
        if beta < 0.8:
            score -= 1
        elif beta > 1.3:
            score += 1

    if volatility_90d is not None and _is_finite(volatility_90d):
        inputs += 1
        if volatility_90d < 1.5:
            score -= 1
        elif volatility_90d > 3.0:
            score += 1

    sec = (stock.sector or "").strip()
    if sec:
        inputs += 1
        if sec in _DEFENSIVE_SECTORS:
            score -= 1
        elif sec in _CYCLICAL_SECTORS:
            score += 1

    mc = stock.market_cap
    if mc is not None:
        if mc > _MEGA_CAP_THRESHOLD:
            score -= 1
        elif mc < 2_000_000_000:
            score += 1

    de = micro.debt_to_equity if micro is not None else None
    if _is_finite(de) and de is not None and de > 200.0:
        score += 1

    or_score = micro.overall_risk if micro is not None else None
    if _is_finite(or_score) and or_score is not None:
        if or_score <= 3:
            score -= 1
        elif or_score >= 8:
            score += 1

    if inputs == 0:
        return "moderate"
    if score <= -1:
        return "conservative"
    if score >= 1:
        return "aggressive"
    return "moderate"


# ---------------------------------------------------------------------------
# Composite + weight renormalisation.
# ---------------------------------------------------------------------------

def _renormalize_weights(sub_scores: Mapping[str, float | None]) -> dict[str, float]:
    """Effective pillar weights with missing-pillar renormalisation.

    Missing (None) pillars are dropped; remaining pillar weights are
    rescaled so they sum to 1.0. This is identical to V1 — the change
    is that V2 only marks a pillar None when ALL its components are
    missing, which is much rarer than V1's "any pillar with no inputs".
    """
    present = {k: PILLAR_WEIGHTS[k] for k, v in sub_scores.items() if v is not None}
    total = sum(present.values())
    if total <= 0:
        return {k: 0.0 for k in PILLAR_WEIGHTS}
    return {k: (present[k] / total if k in present else 0.0) for k in PILLAR_WEIGHTS}


def _compute_volatility_90d(closes: pd.Series | None) -> float | None:
    """90-day daily-return stdev as a percent (e.g. 2.0 means 2.0%/day)."""
    if closes is None or len(closes) < 60:
        return None
    window = closes.iloc[-90:] if len(closes) >= 90 else closes
    rets = window.pct_change().dropna()
    if rets.empty:
        return None
    std = float(rets.std())
    if not _is_finite(std):
        return None
    return std * 100.0


def _last_30d_news_count(ticker: str) -> int | None:
    """Count of news items from the last 30 days. None on fetch failure."""
    try:
        items = stock_news_service.get_news(ticker, limit=50)
    except Exception:  # noqa: BLE001
        return None
    if not items:
        return 0
    today = datetime.now(UTC).date()
    count = 0
    for n in items:
        pub = n.get("published_at")
        if not pub:
            continue
        try:
            d = datetime.fromisoformat(pub.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if (today - d).days <= 30:
            count += 1
    return count


def _load_closes(db: Session, stock_id: int, limit: int = 260) -> pd.Series | None:
    """Ascending close-price series. None if no bars.

    Per-stock SELECT. Used by the single-stock API path
    (`POST /api/stocks/{ticker}/score/recompute`) where one query is
    fine. The bulk recompute_all path uses _bulk_load_recent_bars
    instead to avoid N×SELECT (1100+ queries) — see that function and
    `compute_score(bars=...)` for the fast path.
    """
    rows = db.execute(
        select(OhlcvDaily.close)
        .where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date.asc())
    ).scalars().all()
    if not rows:
        return None
    if len(rows) > limit:
        rows = rows[-limit:]
    return pd.Series([float(c) for c in rows])


def _load_ohlcv_df(db: Session, stock_id: int, limit: int = 260) -> pd.DataFrame | None:
    """Full OHLC frame for ADX. None if no bars.

    Per-stock SELECT. See `_load_closes` note for why recompute_all
    uses the bulk loader instead.
    """
    rows = db.execute(
        select(OhlcvDaily.high, OhlcvDaily.low, OhlcvDaily.close)
        .where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date.asc())
    ).all()
    if not rows:
        return None
    if len(rows) > limit:
        rows = rows[-limit:]
    return pd.DataFrame(
        {
            "high": [float(r[0]) for r in rows],
            "low": [float(r[1]) for r in rows],
            "close": [float(r[2]) for r in rows],
        }
    )


def _bulk_load_recent_bars(
    db: Session, days_back: int = 400
) -> dict[int, list[tuple[float, float, float]]]:
    """Single SELECT pulling the last `days_back` calendar days of OHLCV
    bars for the entire universe, grouped by stock_id.

    Wins over per-stock SELECT (the path compute_score uses for the
    single-stock API endpoint): replaces ~1100 `_load_closes`/`_load_ohlcv_df`
    round-trips with one bulk-cursor pass. Empirical: bulk SELECT of
    ~280k rows on the warm fingerprint completes in ~80-150ms, versus
    ~6-15ms × 2 SELECT × 1100 stocks = 13-33s of cumulative per-stock
    DB time. ~100× faster on the I/O leg.

    `days_back=400` covers ~260 trading days × at-least-65% coverage for
    indicator computation (SMA200, RSI14, ADX14 all fit in a 260-bar
    window). Stocks with less than `days_back` of history return whatever
    they have; indicators that can't compute return None as before.

    Bars come out ordered ASC by date inside each list (matches the
    semantics of the per-stock loaders so downstream code is identical).

    Returns: {stock_id: [(high, low, close), ...]}. Empty dict when no
    bars match the date filter.
    """
    from datetime import date as _date, timedelta as _td

    cutoff = _date.today() - _td(days=days_back)
    rows = db.execute(
        select(
            OhlcvDaily.stock_id,
            OhlcvDaily.date,
            OhlcvDaily.high,
            OhlcvDaily.low,
            OhlcvDaily.close,
        )
        .where(OhlcvDaily.date >= cutoff)
        .order_by(OhlcvDaily.stock_id.asc(), OhlcvDaily.date.asc())
    ).all()
    out: dict[int, list[tuple[float, float, float]]] = {}
    for stock_id, _d, high, low, close in rows:
        out.setdefault(stock_id, []).append((float(high), float(low), float(close)))
    return out


# ---------------------------------------------------------------------------
# Public entry points.
# ---------------------------------------------------------------------------

@dataclass
class _ComputedScore:
    """Internal pre-persistence result."""
    stock_id: int
    composite: float
    sub_scores: dict[str, float | None]
    risk_tier: str
    breakdown: dict[str, Any]
    computed_at: datetime


def _build_score(
    stock: Stock,
    fundamentals: Fundamentals | None,
    closes: pd.Series | None,
    news_count: int | None,
    *,
    ohlcv_df: pd.DataFrame | None = None,
    news_polarity: float | None = None,
    sector_stats: SectorStatsBundle | None = None,
) -> _ComputedScore:
    """Pure compute path — no DB writes, no fundamentals fetch.

    Splitting this out makes tests trivial: stub the inputs, assert the result.
    `compute_score(db, stock)` does the DB+network plumbing.
    """
    micro = fundamentals.micro if fundamentals is not None else None
    last_close = float(closes.iloc[-1]) if closes is not None and len(closes) > 0 else None

    p_score, _, p_break = _profitability(stock, micro, sector_stats)
    su_score, _, su_break = _sustainability(stock, fundamentals, sector_stats)
    g_score, _, g_break = _growth(stock, fundamentals, sector_stats)
    v_score, _, v_break = _value(stock, micro, last_close, sector_stats)
    m_score, _, m_break = _momentum(stock, micro, closes, ohlcv_df)
    s_score, _, s_break = _sentiment(
        stock, fundamentals, last_close,
        news_polarity=news_polarity, news_count=news_count,
    )

    sub: dict[str, float | None] = {
        "profitability": p_score,
        "sustainability": su_score,
        "growth": g_score,
        "value": v_score,
        "momentum": m_score,
        "sentiment": s_score,
    }
    weights = _renormalize_weights(sub)
    composite = sum((sub[k] or 0.0) * weights[k] for k in PILLAR_WEIGHTS)
    composite = _safe_round(composite, 1)

    vol_90d = _compute_volatility_90d(closes)
    risk_tier = _classify_risk(stock, micro, vol_90d)

    breakdown: dict[str, Any] = {
        "profitability": p_break,
        "sustainability": su_break,
        "growth": g_break,
        "value": v_break,
        "momentum": m_break,
        "sentiment": s_break,
        "weights_used": {k: _safe_round(v, 4) for k, v in weights.items()},
        # QW5 — global confidence/coverage. Weighted (by nominal pillar
        # weight) average of each pillar's component-coverage. Honest
        # companion to the missing-data renormalisation: two composites
        # built on different factor bases are NOT comparable, so the UI
        # surfaces how much real data each rests on. Purely additive —
        # does NOT affect `composite` (verified by the QW5 gate: ρ=1.0,
        # tier churn=0).
        "_meta_global": {
            "coverage": _safe_round(
                sum(
                    PILLAR_WEIGHTS[p]
                    * float((brk.get("_meta") or {}).get("coverage", 0.0))
                    for p, brk in (
                        ("profitability", p_break),
                        ("sustainability", su_break),
                        ("growth", g_break),
                        ("value", v_break),
                        ("momentum", m_break),
                        ("sentiment", s_break),
                    )
                ),
                4,
            ),
            "pillars_present": sum(1 for v in sub.values() if v is not None),
            "pillars_total": len(sub),
        },
        "risk_inputs": {
            "beta": _safe_round(micro.beta, 4) if micro and _is_finite(micro.beta) else None,
            "volatility_90d_pct": _safe_round(vol_90d, 4) if vol_90d is not None else None,
            "sector": stock.sector,
            "market_cap": int(stock.market_cap) if stock.market_cap else None,
            "debt_to_equity": _safe_round(micro.debt_to_equity, 4)
                if micro and _is_finite(micro.debt_to_equity) else None,
            "overall_risk": _safe_round(micro.overall_risk, 2)
                if micro and _is_finite(micro.overall_risk) else None,
        },
    }

    return _ComputedScore(
        stock_id=stock.id,
        composite=composite,
        sub_scores=sub,
        risk_tier=risk_tier,
        breakdown=breakdown,
        computed_at=datetime.now(UTC),
    )


def compute_score(
    db: Session,
    stock: Stock,
    *,
    sector_stats: SectorStatsBundle | None = None,
    bars: list[tuple[float, float, float]] | None = None,
) -> StockScore:
    """Compute a fresh StockScore for one stock. NOT persisted.

    Pulls fundamentals from the cache (no network if fresh), recent OHLCV from
    the DB, and a news count + polarity via the news-service cache. The
    caller is expected to UPSERT — see `recompute_all`.

    `bars`: optional pre-loaded `(high, low, close)` tuples in ascending
    date order. When provided, the per-stock OHLCV SELECT is skipped —
    this is what `recompute_all` does after one bulk SELECT to amortise
    the I/O cost across the universe. When None (the single-stock API
    path), we fall back to two per-stock SELECTs as before.
    """
    try:
        fundamentals = stock_fundamentals_service.get_fundamentals(stock.ticker)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[score] fundamentals fetch failed for {stock.ticker}: {exc}")
        fundamentals = None
    if bars is not None:
        # Fast path: use the pre-loaded bars handed in by the bulk caller.
        # Trim to the same 260-bar window as the per-stock loaders to keep
        # indicator results identical (SMA200, MACD slow=26, etc.).
        recent = bars[-260:] if len(bars) > 260 else bars
        if not recent:
            closes = None
            ohlcv_df = None
        else:
            closes = pd.Series([row[2] for row in recent])
            ohlcv_df = pd.DataFrame({
                "high": [row[0] for row in recent],
                "low": [row[1] for row in recent],
                "close": [row[2] for row in recent],
            })
    else:
        closes = _load_closes(db, stock.id)
        ohlcv_df = _load_ohlcv_df(db, stock.id)
    news_count = _last_30d_news_count(stock.ticker)
    _, news_polarity = _aggregate_news_sentiment(stock.ticker, limit=10)

    cs = _build_score(
        stock, fundamentals, closes, news_count,
        ohlcv_df=ohlcv_df, news_polarity=news_polarity,
        sector_stats=sector_stats,
    )
    return StockScore(
        stock_id=cs.stock_id,
        composite=cs.composite,
        # quality kept for backward compat: average of profitability +
        # sustainability (the two pillars that replaced it). Lets old
        # consumers still read a "Quality" number with the same
        # semantics as V3.1 (Q == avg(P, S) is a reasonable proxy).
        quality=(
            (cs.sub_scores["profitability"] + cs.sub_scores["sustainability"]) / 2
            if cs.sub_scores["profitability"] is not None
            and cs.sub_scores["sustainability"] is not None
            else (cs.sub_scores["profitability"] or cs.sub_scores["sustainability"])
        ),
        profitability=cs.sub_scores["profitability"],
        sustainability=cs.sub_scores["sustainability"],
        growth=cs.sub_scores["growth"],
        value=cs.sub_scores["value"],
        momentum=cs.sub_scores["momentum"],
        sentiment=cs.sub_scores["sentiment"],
        risk_tier=cs.risk_tier,
        computed_at=cs.computed_at,
        breakdown=json.dumps(cs.breakdown, allow_nan=False),
    )


# Module-level cache for the sector_stats bundle. The bundle is expensive
# to build (iterates ~1100 stocks, calls get_fundamentals on each — on a
# warm L1/L2 cache that's ~1-2s, on a cold cache 30s+). Medians shift
# slowly (fundamentals refresh ~daily for the few stocks that are stale),
# so a 60-min TTL gives us "instant" pre-pass on consecutive recomputes
# without serving meaningfully stale medians.
#
# Cache key: a fingerprint over (universe-ticker-count, max fetched_at
# across L2 fundamentals). If a single fundamentals row gets refreshed,
# the fingerprint changes and we rebuild. This is conservative — most
# refreshes don't shift any sector median materially — but it's the
# right correctness trade-off vs serving outdated medians.
_SECTOR_STATS_CACHE: dict[str, tuple[float, SectorStatsBundle]] = {}
_SECTOR_STATS_TTL_SECONDS = 60 * 60  # 1 hour


def _sector_stats_cache_key(stocks: list[Stock]) -> str:
    """Fingerprint over the inputs that drive sector_stats. Returns a
    short string; equality means the bundle would be identical.

    Components:
    - count of unique tickers in the universe
    - max FetchCache.fetched_at across kind='fundamentals' rows
    Both queries are aggregate single-pass, ~5-10ms total."""
    from sqlalchemy import func

    from app.core.db import SessionLocal
    from app.models import FetchCache

    n_tickers = len({s.ticker for s in stocks})
    try:
        with SessionLocal() as db:
            max_fetched = db.execute(
                select(func.max(FetchCache.fetched_at)).where(
                    FetchCache.kind == "fundamentals"
                )
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        # If we can't read the DB, fingerprint just by count + clock so
        # we still cache within a single process lifetime.
        import time as _time

        return f"n={n_tickers}|err|t={int(_time.time())}"
    return f"n={n_tickers}|maxL2={max_fetched.isoformat() if max_fetched else 'none'}"


def _build_sector_stats(
    stocks: list[Stock],
    *,
    on_heartbeat=None,
    heartbeat_every: int = 20,
    cancel_check=None,
    use_cache: bool = True,
) -> SectorStatsBundle:
    """Pre-pass: pull cached fundamentals once per ticker, group by
    sector, hand off to sector_stats_service.compute().

    Catalog has duplicate ticker rows (see CLAUDE.md) — we dedupe by
    ticker so a stock with two rows doesn't double-weight in its
    sector's median. Fundamentals fetch failures are silent: a stock
    with no fundamentals just doesn't contribute to any aggregate.

    `on_heartbeat` + `cancel_check` (both optional) let the runner keep
    the persistent toast alive AND react to user cancels while this loop
    runs. Crucial detail: cancel_check is polled EVERY stock (it's a
    cheap set lookup, microseconds), whereas heartbeat fires every
    `heartbeat_every` stocks (each call does a DB commit, milliseconds).
    Decoupling these matters when individual `get_fundamentals` calls
    take seconds (yfinance retries on delisted tickers): without the
    per-stock cancel poll, hitting Stop during the pre-pass takes ~80s
    on average to react. See issue caught 2026-05-11 where the user
    reported "lo stop non funziona" with an 80s gap between last
    heartbeat and the row being marked failed.

    `use_cache=True` consults the module-level _SECTOR_STATS_CACHE first.
    Hit (key matches + within TTL): returns the cached bundle in
    microseconds, no per-stock fetch loop at all. Miss: builds fresh
    and stores. Pass `use_cache=False` to force rebuild — used by
    tests + the `--no-cache` admin path if we ever add one.
    """
    import time as _time

    if use_cache:
        key = _sector_stats_cache_key(stocks)
        cached = _SECTOR_STATS_CACHE.get(key)
        now_t = _time.time()
        if cached is not None:
            cached_at, cached_bundle = cached
            if now_t - cached_at < _SECTOR_STATS_TTL_SECONDS:
                logger.info(
                    f"[score] sector_stats cache HIT (age "
                    f"{int(now_t - cached_at)}s, key={key!r})"
                )
                # Heartbeat once so the runner's stale detector doesn't
                # trip if the pre-pass returns instantly (the caller
                # expects to see at least one heartbeat-tick). Emit
                # (n, n) to signal "100% done" — useful for the toast
                # which renders this as a full bar before the scoring
                # phase begins.
                if on_heartbeat is not None:
                    on_heartbeat(len(stocks), len(stocks))
                return cached_bundle

    by_sector: dict[str, list[Fundamentals]] = {}
    seen_tickers: set[str] = set()
    total_stocks = len(stocks)
    for i, stock in enumerate(stocks):
        # Cancel: polled EVERY stock (microseconds — Python set lookup).
        # Lower latency on Stop than the heartbeat-tied check we used
        # before, especially in the pre-pass where individual fetches
        # can stall for seconds on yfinance retries.
        if cancel_check is not None and cancel_check():
            raise RecomputeCancelled()
        # Heartbeat: every `heartbeat_every` stocks (each call commits
        # the DB, more expensive). 20 means ~1 heartbeat per 5-10s of
        # pre-pass wall time on a warm cache — well within the 120s
        # stale threshold. The callback receives (stocks_done,
        # stocks_total) so the runner can translate this into the
        # appropriate UI denominator (e.g. linear-interpolate to a
        # "sectors processed" count for the toast).
        if on_heartbeat is not None and i % heartbeat_every == 0:
            on_heartbeat(i, total_stocks)
        if stock.ticker in seen_tickers:
            continue
        seen_tickers.add(stock.ticker)
        try:
            funds = stock_fundamentals_service.get_fundamentals(stock.ticker)
        except Exception:  # noqa: BLE001
            funds = None
        if funds is None:
            continue
        by_sector.setdefault(stock.sector or "", []).append(funds)
    # Final heartbeat at the end of the loop so the runner has fresh
    # data before sector_stats_service.compute() runs (~10ms but still).
    if on_heartbeat is not None:
        on_heartbeat(total_stocks, total_stocks)
    bundle = sector_stats_service.compute(by_sector)
    n_with_stats = sum(
        1 for s in bundle.by_sector.values()
        if any(getattr(s, f) is not None for f in (
            "pe_median", "pb_median", "roe_median", "revenue_growth_median",
        ))
    )
    logger.info(
        f"[score] sector_stats: {len(bundle.by_sector)} sectors, "
        f"{n_with_stats} with publishable medians, universe.n={bundle.universe.n}"
    )
    if use_cache:
        # Store under the fingerprint we computed at entry. Next call
        # within TTL with same fingerprint returns this bundle instantly.
        key = _sector_stats_cache_key(stocks)
        _SECTOR_STATS_CACHE[key] = (_time.time(), bundle)
    return bundle


def clear_sector_stats_cache() -> None:
    """Drop the module-level sector_stats cache. Used by tests to keep
    them isolated, and exposed for any future "force fresh medians"
    admin path."""
    _SECTOR_STATS_CACHE.clear()


class RecomputeCancelled(Exception):
    """Raised by recompute_all when the cancel_check callback returns True.

    The runner (score_runner.run_tracked_recompute) catches it and marks
    the associated ScanRun as failed with a user-friendly message — same
    pattern as ScanCancelled in scan_service."""


def recompute_all(
    db: Session,
    *,
    on_progress=None,
    on_phase_change=None,
    progress_every: int = 10,
    cancel_check=None,
) -> tuple[int, int]:
    """Batch UPSERT scores for every stock. Returns (ok, failed).

    Earlier versions (yesterday, May 2026 morning) carried an
    incremental-skip optimisation that compared `score.computed_at`
    against `fundamentals.fetched_at` + `max(ohlcv.date)` and skipped
    stocks whose inputs hadn't moved. We removed it because:

      1. Manual user trigger ("Ricalcola score" on the homepage) was
         the painful case — consecutive clicks reported "1097 saltati,
         0 processati" because the inputs hadn't budged since the
         previous run. Felt broken even though it was technically
         correct.
      2. The automatic post-scan path didn't actually benefit much:
         every scan adds new OHLCV bars before triggering this, so on
         a fresh scan the skip-decision returns False for ~everyone
         anyway. The savings only materialised on consecutive same-
         day re-scans with no new bars — a real but narrow case.
      3. The supporting code (3 aggregate SQL queries + a 35-line
         decision function + a class to thread the state) was ~100
         LOC of cognitive overhead for the ~3s saving in the narrow
         case.

    Going forward every call re-scores every stock. The sector_stats
    pre-pass + per-stock compute_score remain unchanged.

    Two-phase to use *real* sector medians instead of static V1 values:
      1. Pre-pass: collect fundamentals (cache hit on the fast path) →
         compute sector_stats bundle (medians of P/E, P/B, ROE, growth,
         margins per sector + universe fallback).
      2. Score loop: pass the bundle to each compute_score so the
         value/quality/growth pillars benchmark each stock against its
         peer median rather than the hardcoded baseline.

    Persists incrementally (commit after each successful score) and uses
    `db.merge()` for true UPSERT semantics.

    Does NOT raise on per-stock failure — logs and continues.

    Progress + cancel hooks (added so the user-triggered "Ricalcola score"
    flow can drive the same persistent-toast UX as a scan):
      - `on_progress(done, total)` fires per heartbeat with the appropriate
        denominator for the active phase. During the sector_stats pre-pass
        `total` is the unique-sectors count and `done` advances from 0→N
        proportional to the per-stock aggregation progress (so the bar
        actually moves during the pre-pass — pre-May-2026 it sat at 0/N
        which was confusing). During the scoring loop `total` is the
        stock count and `done` is stocks scored.
      - `on_phase_change(phase)` fires once per phase transition with
        either "sector_stats" or "scoring". Runners use this to drive
        the toast's phase label + reset its per-phase ETA timer. Without
        this callback the runner used to flip phase based on `done > 0`,
        but that conflicts with the new "done moves during pre-pass too"
        behaviour.
      - `cancel_check()` is polled every stock during pre-pass + every
        `progress_every` stocks during scoring; returning True raises
        `RecomputeCancelled` from inside the loop.
    All three default to no-op when omitted — keeps the cron call-sites
    untouched.
    """
    stocks = db.execute(select(Stock)).scalars().all()
    total = len(stocks)

    # Count unique sectors so the pre-pass progress bar can render
    # "K/N sectors" with N = real-world denominator the user expects
    # (~12 GICS top-level sectors). Without this the bar would either
    # sit at 0/total_stocks (pre-2026) or 0/0 (no useful denominator).
    sector_count = len({s.sector for s in stocks if s.sector}) or 1

    # Phase transition: pre-pass begins.
    if on_phase_change is not None:
        on_phase_change("sector_stats")
    # Seed total = sector_count so the toast immediately renders the
    # right denominator. `done=0` at start; the pre-pass heartbeat
    # below interpolates the stock-level progress onto sector units.
    if on_progress is not None:
        on_progress(0, sector_count)

    # Pre-pass: build sector_stats. Cost is usually negligible (L1/L2
    # cache for ~889 tickers, ~50ms) BUT can spike to 30s+ when delisted
    # tickers force yfinance retries. Thread `on_heartbeat` + `cancel_check`
    # through so the runner can keep its ScanRun row's heartbeat fresh
    # during the slow loop — without it the stale detector (>120s)
    # force-closes the row before the score loop ever starts.
    def _prepass_heartbeat(done_stocks: int, total_stocks: int) -> None:
        if on_progress is None:
            return
        # Linear interpolate the per-stock progress onto the sector
        # denominator. The actual sector_stats compute() runs all-at-
        # once at the very end of the pre-pass, but the user reads
        # "calcolo mediane settoriali" as "N sectors being processed"
        # — the interpolation matches that mental model and lets the
        # bar actually move during the ~5-30s pre-pass wall time.
        denom = max(1, total_stocks)
        sectors_done = min(sector_count, int(done_stocks / denom * sector_count))
        on_progress(sectors_done, sector_count)

    sector_stats = _build_sector_stats(
        list(stocks),
        on_heartbeat=_prepass_heartbeat,
        cancel_check=cancel_check,
    )

    # Phase transition: scoring begins. Total flips from sector_count
    # to total_stocks (the bar visually resets from 100% pre-pass to
    # 0% of scoring — same UX as a multi-step installer).
    if on_phase_change is not None:
        on_phase_change("scoring")
    if on_progress is not None:
        on_progress(0, total)

    # Bulk-load all recent OHLCV bars in ONE SELECT instead of the
    # per-stock pair (`_load_closes` + `_load_ohlcv_df`). Empirical: on
    # ~1100 stocks the old path spent ~13-33s of cumulative SELECT time;
    # the bulk version is ~80-150ms total. The 400-day window covers
    # the 260 trading days that compute_score's indicators need.
    bars_by_stock = _bulk_load_recent_bars(db, days_back=400)

    seen_ids: set[int] = set()
    ok = 0
    failed = 0
    # Commit batching: one fsync per N stocks instead of per-stock saves
    # ~3-10ms × N. We keep N small enough that a Stop click only loses
    # the in-flight batch (~50 stocks of work, <1s on the fast path).
    BATCH_COMMIT_EVERY = 50
    pending_in_batch = 0

    for i, stock in enumerate(stocks):
        # Cooperative cancel: polled EVERY stock (cheap set lookup) so
        # Stop reacts within one stock of the user click — even when
        # individual compute_score calls are slow (e.g. fundamentals
        # cache miss triggering a yfinance retry chain). The cost of
        # the check itself is negligible vs the per-stock work.
        if cancel_check is not None and cancel_check():
            # Flush any pending batch before raising so partial progress
            # is persisted (not strictly necessary — the runner marks
            # the run failed anyway — but cheap and helpful for debug).
            if pending_in_batch > 0:
                try:
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
            raise RecomputeCancelled()
        if stock.id in seen_ids:
            continue
        seen_ids.add(stock.id)

        try:
            new_score = compute_score(
                db,
                stock,
                sector_stats=sector_stats,
                bars=bars_by_stock.get(stock.id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] compute_score failed for {stock.ticker}: {exc}")
            failed += 1
            continue
        try:
            db.merge(new_score)
            ok += 1
            pending_in_batch += 1
            # Commit batch when the threshold hits — eliminates ~95% of
            # the fsync overhead on the recompute loop.
            if pending_in_batch >= BATCH_COMMIT_EVERY:
                db.commit()
                pending_in_batch = 0
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] persist failed for {stock.ticker}: {exc}")
            db.rollback()
            pending_in_batch = 0
            failed += 1
        # Heartbeat every `progress_every` stocks (and once at the end).
        if on_progress is not None and (i % progress_every == 0 or i == total - 1):
            on_progress(i + 1, total)

    # Final flush — the tail < BATCH_COMMIT_EVERY won't trigger a commit
    # inside the loop, so make sure those rows land before we return.
    if pending_in_batch > 0:
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] final batch commit failed: {exc}")
            db.rollback()

    logger.info(
        f"[score] recompute_all: ok={ok} failed={failed} (of {total} stocks)"
    )
    return ok, failed
