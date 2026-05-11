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
from app.indicators.sma import sma as sma_indicator
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
    breakdown["_meta"] = {
        "components_present": n_present,
        "components_total": len(components),
        "weight_sum_present": _safe_round(den, 4),
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
        0.22,
        sector_median=_med("roe_median"),
    ))
    components.append(_Component(
        "roa", micro.return_on_assets,
        _blended_hib(micro.return_on_assets, _med("roa_median"),
                     abs_full=0.10, abs_half=0.05, abs_zero=0.0,
                     rel_full_pp=0.025),
        0.15,
        sector_median=_med("roa_median"),
    ))
    components.append(_Component(
        "profit_margin", micro.profit_margins,
        _blended_hib(micro.profit_margins, _med("profit_margin_median"),
                     abs_full=0.20, abs_half=0.10, abs_zero=0.0,
                     rel_full_pp=0.05),
        0.20,
        sector_median=_med("profit_margin_median"),
    ))
    components.append(_Component(
        "operating_margin", micro.operating_margins,
        _blended_hib(micro.operating_margins, _med("operating_margin_median"),
                     abs_full=0.20, abs_half=0.10, abs_zero=0.0,
                     rel_full_pp=0.05),
        0.15,
        sector_median=_med("operating_margin_median"),
    ))
    components.append(_Component(
        "gross_margin", micro.gross_margins,
        _blended_hib(micro.gross_margins, _med("gross_margin_median"),
                     abs_full=0.50, abs_half=0.30, abs_zero=0.10,
                     rel_full_pp=0.10),
        0.13,
        sector_median=_med("gross_margin_median"),
    ))
    components.append(_Component(
        "insider_holdings", micro.held_percent_insiders,
        _ramp3(micro.held_percent_insiders, full=0.10, half=0.03, zero=0.0)
        if _is_finite(micro.held_percent_insiders) else None,
        0.07,
    ))
    components.append(_Component(
        "institutional_holdings", micro.held_percent_institutions,
        _ramp3(micro.held_percent_institutions, full=0.70, half=0.40, zero=0.10)
        if _is_finite(micro.held_percent_institutions) else None,
        0.08,
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
    """Linear regression slope of profit_margin over the last 3 annual
    reports. Returns slope in fraction-per-year units; +0.02 is a
    +2pp/year improvement. Returns None below 3 data points.
    """
    annual = getattr(fundamentals, "annual", None) or []
    margins: list[float] = []
    for a in annual[-3:]:
        rev = getattr(a, "revenue", None)
        ni = getattr(a, "net_income", None)
        if not _is_finite(rev) or not _is_finite(ni) or rev is None or float(rev) <= 0:
            continue
        margins.append(float(ni) / float(rev))
    if len(margins) < 3:
        return None
    n = len(margins)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(margins) / n
    num = sum((xs[i] - x_mean) * (margins[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


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

    Components:
      - Revenue growth (YoY)        (0.25)  HIB blend, abs full@20%/half@0/zero@-10%, rel +5pp
      - Earnings growth (YoY)       (0.25)  HIB blend, abs full@20%/half@0/zero@-10%, rel +5pp
      - Quarterly earnings growth   (0.15)  HIB blend, abs full@25%/half@0/zero@-15%, rel +10pp
      - EPS forward vs trailing     (0.10)  HIB absolute (no sector aggregate)
      - Earnings beats (last 4 q)   (0.15)  HIB absolute (no sector aggregate)
      - Revenue trend (3y CAGR)     (0.10)  HIB absolute (no sector aggregate)
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
        0.25,
    sector_median=_med("revenue_growth_median"),
    ))
    eg = micro.earnings_growth if micro else None
    components.append(_Component(
        "earnings_growth", eg,
        _blended_hib(eg, _med("earnings_growth_median"),
                     abs_full=0.20, abs_half=0.0, abs_zero=-0.10,
                     rel_full_pp=0.05),
        0.25,
    sector_median=_med("earnings_growth_median"),
    ))
    qeg = micro.earnings_quarterly_growth if micro else None
    components.append(_Component(
        "qoq_earnings_growth", qeg,
        _blended_hib(qeg, _med("earnings_quarterly_growth_median"),
                     abs_full=0.25, abs_half=0.0, abs_zero=-0.15,
                     rel_full_pp=0.10),
        0.15,
    sector_median=_med("earnings_quarterly_growth_median"),
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
        0.10,
    ))

    # --- Earnings-beats history (no sector aggregate) --------------------
    earnings = fundamentals.earnings or []
    last4 = [e for e in earnings if e.eps_reported is not None and e.eps_estimate is not None][-4:]
    if last4:
        beats = sum(1 for e in last4 if e.eps_reported > e.eps_estimate)
        beat_score = _ramp3(float(beats), full=4.0, half=2.0, zero=0.0)
        components.append(_Component("earnings_beats", beats, beat_score, 0.15))
    else:
        components.append(_Component("earnings_beats", None, None, 0.15))

    # --- Multi-year revenue CAGR (no sector aggregate) -------------------
    annual = fundamentals.annual or []
    revs = [a.revenue for a in annual if a.revenue is not None and a.revenue > 0]
    cagr = None
    if len(revs) >= 3:
        first = float(revs[-3])
        last = float(revs[-1])
        if first > 0:
            try:
                cagr = (last / first) ** (1.0 / 2.0) - 1.0
            except (ValueError, ZeroDivisionError):
                cagr = None
    components.append(_Component(
        "revenue_cagr_3y", cagr,
        _ramp3(cagr, full=0.15, half=0.05, zero=-0.05) if cagr is not None else None,
        0.10,
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
        0.22,
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
        0.18,
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
        0.10,
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

    # --- Payout ratio sanity (no sector aggregate; healthy 30-60% band) -
    pr = micro.payout_ratio
    pr_score = None
    if _is_finite(pr) and pr is not None and (dy_pct is not None and dy_pct > 0):
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
    components.append(_Component("payout_ratio", pr if dy_pct else None, pr_score, 0.07))

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
      - Trend: SMA20 > SMA50 > SMA200  (0.12)  staircase (1.0/0.66/0.33/0.0)
      - Price vs SMA200           (0.10)  full @ +15%, half @ 0%, zero @ -15%
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

    # --- Trend stacking: SMA20 > SMA50 > SMA200 --------------------------
    trend_score: float | None = None
    sma20_v = sma50_v = sma200_v = None
    last_close = float(closes.iloc[-1]) if closes_present and closes is not None else None
    if closes_present and closes is not None and len(closes) >= 200:
        try:
            sma20_v = float(sma_indicator(closes, 20).iloc[-1])
            sma50_v = float(sma_indicator(closes, 50).iloc[-1])
            sma200_v = float(sma_indicator(closes, 200).iloc[-1])
            if all(pd.notna(v) for v in (sma20_v, sma50_v, sma200_v)) and last_close is not None:
                # Score 0..3 of "stacked correctly" rules.
                rules = [
                    last_close > sma20_v,
                    sma20_v > sma50_v,
                    sma50_v > sma200_v,
                ]
                trend_score = 100.0 * sum(1 for r in rules if r) / 3.0
        except Exception:  # noqa: BLE001
            trend_score = None
    components.append(_Component(
        "trend_stack",
        {"close": _safe_round(last_close or 0.0, 2),
         "sma20": _safe_round(sma20_v or 0.0, 2),
         "sma50": _safe_round(sma50_v or 0.0, 2),
         "sma200": _safe_round(sma200_v or 0.0, 2)} if trend_score is not None else None,
        trend_score,
        0.12,
    ))

    # --- Price vs SMA200 -------------------------------------------------
    px_vs_sma200: float | None = None
    if sma200_v is not None and last_close is not None and pd.notna(sma200_v) and sma200_v > 0:
        px_vs_sma200 = (last_close - sma200_v) / sma200_v
    components.append(_Component(
        "price_vs_sma200", px_vs_sma200,
        _ramp3(px_vs_sma200, full=0.15, half=0.0, zero=-0.15) if px_vs_sma200 is not None else None,
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
    rel_strength: float | None = None
    if (
        micro is not None
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
        0.30,
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
        0.18,
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
    components.append(_Component("short_percent_of_float", spf, spf_score, 0.05))

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
    """Ascending close-price series. None if no bars."""
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
    """Full OHLC frame for ADX. None if no bars."""
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


def compute_score(db: Session, stock: Stock, *, sector_stats: SectorStatsBundle | None = None) -> StockScore:
    """Compute a fresh StockScore for one stock. NOT persisted.

    Pulls fundamentals from the cache (no network if fresh), recent OHLCV from
    the DB, and a news count + polarity via the news-service cache. The
    caller is expected to UPSERT — see `recompute_all`.
    """
    try:
        fundamentals = stock_fundamentals_service.get_fundamentals(stock.ticker)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[score] fundamentals fetch failed for {stock.ticker}: {exc}")
        fundamentals = None
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


def _build_sector_stats(
    stocks: list[Stock],
    *,
    on_heartbeat=None,
    heartbeat_every: int = 20,
    cancel_check=None,
) -> SectorStatsBundle:
    """Pre-pass: pull cached fundamentals once per ticker, group by
    sector, hand off to sector_stats_service.compute().

    Catalog has duplicate ticker rows (see CLAUDE.md) — we dedupe by
    ticker so a stock with two rows doesn't double-weight in its
    sector's median. Fundamentals fetch failures are silent: a stock
    with no fundamentals just doesn't contribute to any aggregate.

    `on_heartbeat` + `cancel_check` (both optional) let the runner keep
    the persistent toast alive while this loop runs. Crucial: for ~10
    delisted tickers yfinance retries each call ~5x before giving up,
    so without heartbeats the toast's stale detector (>120s without
    progress) force-closes the run during the pre-pass — even though
    the worker is alive and progressing. See issue caught 2026-05-11
    where two consecutive recomputes failed at +0.7s heartbeat.
    """
    by_sector: dict[str, list[Fundamentals]] = {}
    seen_tickers: set[str] = set()
    for i, stock in enumerate(stocks):
        if cancel_check is not None and i % heartbeat_every == 0 and cancel_check():
            raise RecomputeCancelled()
        if on_heartbeat is not None and i % heartbeat_every == 0:
            on_heartbeat()
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
        on_heartbeat()
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
    return bundle


class RecomputeCancelled(Exception):
    """Raised by recompute_all when the cancel_check callback returns True.

    The runner (score_runner.run_tracked_recompute) catches it and marks
    the associated ScanRun as failed with a user-friendly message — same
    pattern as ScanCancelled in scan_service."""


def recompute_all(
    db: Session,
    *,
    on_progress=None,
    progress_every: int = 10,
    cancel_check=None,
) -> tuple[int, int]:
    """Batch UPSERT scores for every stock. Returns (ok, failed) counts.

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
      - `on_progress(done, total)` fires every `progress_every` stocks
        and once at the very start to seed `progress_total`.
      - `cancel_check()` is polled every `progress_every` stocks; returning
        True raises `RecomputeCancelled` from inside the loop.
    Both default to no-op when omitted — keeps the cron-call sites
    untouched. Returns (ok, failed) as a tuple now (was scalar `ok`)
    so the runner can surface both in the ScanRun summary.
    """
    stocks = db.execute(select(Stock)).scalars().all()
    total = len(stocks)

    # Seed total before the sector_stats pre-pass so the UI shows the
    # correct denominator immediately. `done=0` until the score loop
    # actually starts touching stocks.
    if on_progress is not None:
        on_progress(0, total)

    # Pre-pass: build sector_stats. Cost is usually negligible (L1/L2
    # cache for ~889 tickers, ~50ms) BUT can spike to 30s+ when delisted
    # tickers force yfinance retries. Thread `on_heartbeat` + `cancel_check`
    # through so the runner can keep its ScanRun row's heartbeat fresh
    # during the slow loop — without it the stale detector (>120s)
    # force-closes the row before the score loop ever starts.
    def _prepass_heartbeat() -> None:
        # The runner's on_progress treats done=0/total=N as "still in
        # sector_stats phase, bump heartbeat only". See score_runner.
        if on_progress is not None:
            on_progress(0, total)

    sector_stats = _build_sector_stats(
        list(stocks),
        on_heartbeat=_prepass_heartbeat,
        cancel_check=cancel_check,
    )

    seen_ids: set[int] = set()
    ok = 0
    failed = 0

    for i, stock in enumerate(stocks):
        # Cooperative cancel: polled every `progress_every` stocks so a
        # long score loop can still bail within a fraction of a second.
        if cancel_check is not None and i % progress_every == 0 and cancel_check():
            raise RecomputeCancelled()
        if stock.id in seen_ids:
            continue
        seen_ids.add(stock.id)
        try:
            new_score = compute_score(db, stock, sector_stats=sector_stats)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] compute_score failed for {stock.ticker}: {exc}")
            failed += 1
            continue
        try:
            db.merge(new_score)
            db.commit()
            ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] persist failed for {stock.ticker}: {exc}")
            db.rollback()
            failed += 1
        # Heartbeat every `progress_every` stocks (and once at the end).
        if on_progress is not None and (i % progress_every == 0 or i == total - 1):
            on_progress(i + 1, total)

    if failed:
        logger.info(f"[score] recompute_all: ok={ok} failed={failed}")
    else:
        logger.info(f"[score] recompute_all: ok={ok}")
    return ok, failed
