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

PILLAR_WEIGHTS: dict[str, float] = {
    "quality": 0.25,
    "growth": 0.25,
    "value": 0.15,
    "momentum": 0.20,
    "sentiment": 0.15,
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
    `raw` is the original input value, retained for the breakdown JSON
    so the UI can render the actual number alongside the score.
    """
    name: str
    raw: Any
    score: float | None
    weight: float


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
# Quality pillar.
# ---------------------------------------------------------------------------

def _quality(stock: Stock, micro: MicroData | None, sector_stats: SectorStatsBundle | None = None) -> tuple[float | None, float, dict]:
    """Components (weights add to 1.0):

      - ROE                       (0.16)  full @ 20%, half @ 10%, zero @ 0%
      - ROA                       (0.10)  full @ 10%, half @ 5%, zero @ 0%
      - Profit margin             (0.12)  full @ 20%, half @ 10%, zero @ 0%
      - Operating margin          (0.10)  full @ 20%, half @ 10%, zero @ 0%
      - Gross margin              (0.06)  full @ 50%, half @ 30%, zero @ 10%
      - Free cash flow positive   (0.10)  binary
      - Debt / Equity             (0.10)  full @ ≤50%, half @ 100%, zero @ 200%
      - Current ratio             (0.06)  full @ 2, half @ 1, zero @ 0.7
      - Quick ratio               (0.05)  full @ 1.5, half @ 1, zero @ 0.5
      - Yahoo overall_risk        (0.05)  1 (best) → full, 10 (worst) → zero
      - Insider holdings          (0.05)  full @ 10%, half @ 3%, zero @ 0%
      - Institutional holdings    (0.05)  full @ 70%, half @ 40%, zero @ 10%

    Each component score is 0-100; pillar = weighted average over present
    components. Missing inputs are SKIPPED rather than scored zero.
    """
    if micro is None:
        return None, 100.0, {}

    components: list[_Component] = []

    # --- Profitability ----------------------------------------------------
    components.append(_Component(
        "roe", micro.return_on_equity,
        _ramp3(micro.return_on_equity, full=0.20, half=0.10, zero=0.0)
        if _is_finite(micro.return_on_equity) else None,
        0.16,
    ))
    components.append(_Component(
        "roa", micro.return_on_assets,
        _ramp3(micro.return_on_assets, full=0.10, half=0.05, zero=0.0)
        if _is_finite(micro.return_on_assets) else None,
        0.10,
    ))
    components.append(_Component(
        "profit_margin", micro.profit_margins,
        _ramp3(micro.profit_margins, full=0.20, half=0.10, zero=0.0)
        if _is_finite(micro.profit_margins) else None,
        0.12,
    ))
    components.append(_Component(
        "operating_margin", micro.operating_margins,
        _ramp3(micro.operating_margins, full=0.20, half=0.10, zero=0.0)
        if _is_finite(micro.operating_margins) else None,
        0.10,
    ))
    components.append(_Component(
        "gross_margin", micro.gross_margins,
        _ramp3(micro.gross_margins, full=0.50, half=0.30, zero=0.10)
        if _is_finite(micro.gross_margins) else None,
        0.06,
    ))

    # --- Cash flow --------------------------------------------------------
    fcf = micro.free_cashflow
    components.append(_Component(
        "fcf", fcf,
        (100.0 if fcf > 0 else 0.0) if _is_finite(fcf) else None,
        0.10,
    ))

    # --- Leverage / liquidity --------------------------------------------
    # yfinance returns debt_to_equity as a percent (145.2 == 1.45).
    components.append(_Component(
        "debt_equity", micro.debt_to_equity,
        _ramp3(micro.debt_to_equity, full=50.0, half=100.0, zero=200.0)
        if _is_finite(micro.debt_to_equity) else None,
        0.10,
    ))
    components.append(_Component(
        "current_ratio", micro.current_ratio,
        _ramp3(micro.current_ratio, full=2.0, half=1.0, zero=0.7)
        if _is_finite(micro.current_ratio) else None,
        0.06,
    ))
    components.append(_Component(
        "quick_ratio", micro.quick_ratio,
        _ramp3(micro.quick_ratio, full=1.5, half=1.0, zero=0.5)
        if _is_finite(micro.quick_ratio) else None,
        0.05,
    ))

    # --- Governance / ownership ------------------------------------------
    # Yahoo's overall_risk is on a 1 (best) – 10 (worst) scale.
    components.append(_Component(
        "overall_risk", micro.overall_risk,
        _ramp(micro.overall_risk, full=1.0, zero=10.0) if _is_finite(micro.overall_risk) else None,
        0.05,
    ))
    components.append(_Component(
        "insider_holdings", micro.held_percent_insiders,
        _ramp3(micro.held_percent_insiders, full=0.10, half=0.03, zero=0.0)
        if _is_finite(micro.held_percent_insiders) else None,
        0.05,
    ))
    components.append(_Component(
        "institutional_holdings", micro.held_percent_institutions,
        _ramp3(micro.held_percent_institutions, full=0.70, half=0.40, zero=0.10)
        if _is_finite(micro.held_percent_institutions) else None,
        0.05,
    ))

    # --- Sector-relative ROE ---------------------------------------------
    # Same input as the absolute ROE lane above, but scored against the
    # stock's *peers*. A 15% ROE in Tech (peer median ~22%) is mediocre;
    # the same 15% in Utilities (peer median ~9%) is excellent. The
    # absolute lane already captures "is this a good business in absolute
    # terms"; this lane captures "is this a good business *for its
    # peers*" — orthogonal information that catches sector-mean reversion
    # opportunities. See `services/sector_stats_service.py`.
    sector_roe_med = (
        sector_stats.resolve(stock.sector, "roe_median")
        if sector_stats is not None else None
    )
    roe_vs_sector_diff: float | None = None
    if (
        _is_finite(micro.return_on_equity)
        and sector_roe_med is not None
        and _is_finite(sector_roe_med)
    ):
        roe_vs_sector_diff = float(micro.return_on_equity) - float(sector_roe_med)
    components.append(_Component(
        "roe_vs_sector",
        {
            "roe": _safe_round(micro.return_on_equity, 4) if _is_finite(micro.return_on_equity) else None,
            "sector_median": _safe_round(sector_roe_med, 4) if sector_roe_med is not None else None,
            "diff": _safe_round(roe_vs_sector_diff, 4) if roe_vs_sector_diff is not None else None,
        } if roe_vs_sector_diff is not None else None,
        # ramp: +5pp above peer median = full, par = half, -5pp below = zero
        _ramp3(roe_vs_sector_diff, full=0.05, half=0.0, zero=-0.05)
        if roe_vs_sector_diff is not None else None,
        0.05,
    ))

    return _aggregate(components)


# ---------------------------------------------------------------------------
# Growth pillar.
# ---------------------------------------------------------------------------

def _growth(stock: Stock, fundamentals: Fundamentals | None, sector_stats: SectorStatsBundle | None = None) -> tuple[float | None, float, dict]:
    """Components:

      - Revenue growth (YoY)        (0.25)  full @ 20%, half @ 0%, zero @ -10%
      - Earnings growth (YoY)       (0.25)  full @ 20%, half @ 0%, zero @ -10%
      - Quarterly earnings growth   (0.15)  full @ 25%, half @ 0%, zero @ -15%
      - EPS forward vs trailing     (0.10)  full @ +20%, half @ 0%, zero @ -10%
      - Earnings beats (last 4 q)   (0.15)  full = 4/4, half = 2/4, zero = 0/4
      - Revenue trend (3y CAGR)     (0.10)  full @ 15%, half @ 5%, zero @ -5%
    """
    if fundamentals is None:
        return None, 100.0, {}
    micro = fundamentals.micro

    components: list[_Component] = []

    # --- Revenue & earnings YoY ------------------------------------------
    rg = micro.revenue_growth if micro else None
    components.append(_Component(
        "revenue_growth", rg,
        _ramp3(rg, full=0.20, half=0.0, zero=-0.10) if _is_finite(rg) else None,
        0.25,
    ))
    eg = micro.earnings_growth if micro else None
    components.append(_Component(
        "earnings_growth", eg,
        _ramp3(eg, full=0.20, half=0.0, zero=-0.10) if _is_finite(eg) else None,
        0.25,
    ))
    qeg = micro.earnings_quarterly_growth if micro else None
    components.append(_Component(
        "qoq_earnings_growth", qeg,
        _ramp3(qeg, full=0.25, half=0.0, zero=-0.15) if _is_finite(qeg) else None,
        0.15,
    ))

    # --- Forward EPS vs trailing EPS -------------------------------------
    eps_t = micro.eps_trailing if micro else None
    eps_f = micro.eps_forward if micro else None
    fwd_growth: float | None = None
    if _is_finite(eps_t) and _is_finite(eps_f) and eps_t and eps_t > 0:
        fwd_growth = (float(eps_f) - float(eps_t)) / float(eps_t)
    components.append(_Component(
        "eps_forward_growth", fwd_growth,
        _ramp3(fwd_growth, full=0.20, half=0.0, zero=-0.10) if fwd_growth is not None else None,
        0.10,
    ))

    # --- Earnings-beats history ------------------------------------------
    earnings = fundamentals.earnings or []
    last4 = [e for e in earnings if e.eps_reported is not None and e.eps_estimate is not None][-4:]
    if last4:
        beats = sum(1 for e in last4 if e.eps_reported > e.eps_estimate)
        # Linear-ish ramp through full=4/half=2/zero=0.
        beat_score = _ramp3(float(beats), full=4.0, half=2.0, zero=0.0)
        components.append(_Component("earnings_beats", beats, beat_score, 0.15))
    else:
        components.append(_Component("earnings_beats", None, None, 0.15))

    # --- Multi-year revenue CAGR (from annual income statement) ----------
    annual = fundamentals.annual or []
    revs = [a.revenue for a in annual if a.revenue is not None and a.revenue > 0]
    cagr: float | None = None
    if len(revs) >= 3:
        # Take the last 3 annual rows and compute CAGR over the 2-year span.
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

    # --- Sector-relative revenue growth ----------------------------------
    # Same logic as roe_vs_sector but on the YoY revenue-growth axis. A
    # 12% grower in semis (peer median ~22%) is below par; the same 12%
    # in utilities (peer median ~3%) is excellent. Catches sector-mean
    # convergence trades.
    sector_rev_med = (
        sector_stats.resolve(stock.sector, "revenue_growth_median")
        if sector_stats is not None else None
    )
    rev_vs_sector_diff: float | None = None
    if (
        rg is not None and _is_finite(rg)
        and sector_rev_med is not None and _is_finite(sector_rev_med)
    ):
        rev_vs_sector_diff = float(rg) - float(sector_rev_med)
    components.append(_Component(
        "revenue_growth_vs_sector",
        {
            "revenue_growth": _safe_round(rg, 4) if _is_finite(rg) else None,
            "sector_median": _safe_round(sector_rev_med, 4) if sector_rev_med is not None else None,
            "diff": _safe_round(rev_vs_sector_diff, 4) if rev_vs_sector_diff is not None else None,
        } if rev_vs_sector_diff is not None else None,
        # ramp: +5pp above peer = full, par = half, -5pp below = zero
        _ramp3(rev_vs_sector_diff, full=0.05, half=0.0, zero=-0.05)
        if rev_vs_sector_diff is not None else None,
        0.05,
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
    """Components (weights sum to 1.0):

      - P/E (TTM) vs sector median  (0.22)  full @ ≤median, zero @ 2× median
      - Forward P/E vs sector med   (0.10)  same shape, on forward earnings
      - PEG (or trailing PEG)       (0.18)  full @ ≤1, half @ 2, zero @ ≥3
      - P/B vs sector P/B median    (0.10)  full @ ≤median, zero @ 2× median
      - P/S                         (0.08)  full @ ≤2, half @ 5, zero @ 10
      - EV / EBITDA                 (0.10)  full @ ≤8, half @ 14, zero @ 25
      - EV / Revenue                (0.05)  full @ ≤2, half @ 5, zero @ 10
      - Dividend yield              (0.10)  full @ ≥3%, zero @ 0%
      - Payout ratio sanity         (0.07)  best 30-60%, drops outside.
    """
    if micro is None:
        return None, 100.0, {}

    # Prefer dynamic sector medians from the live universe (via
    # sector_stats_service). When the bundle is missing or thin (sector
    # below the min-N threshold), fall back to the V1 hardcoded baseline
    # — that's the whole reason the static maps still live in this module.
    sector_pe_dynamic = (
        sector_stats.resolve(stock.sector, "pe_median")
        if sector_stats is not None else None
    )
    sector_pb_dynamic = (
        sector_stats.resolve(stock.sector, "pb_median")
        if sector_stats is not None else None
    )
    sector_pe = sector_pe_dynamic if sector_pe_dynamic is not None else         _SECTOR_PE_MEDIAN.get(stock.sector or "", _UNIVERSE_PE_MEDIAN)
    sector_pb = sector_pb_dynamic if sector_pb_dynamic is not None else         _SECTOR_PB_MEDIAN.get(stock.sector or "", _UNIVERSE_PB_MEDIAN)
    components: list[_Component] = []

    def _multiple_vs_median(val: float | None, median: float) -> float | None:
        """Map a positive multiple to a 0-100 score, full at-or-below median,
        zero at 2× median, linear in between. Negative / non-finite → None."""
        if not _is_finite(val) or val is None or val <= 0:
            return None
        if val <= median:
            return 100.0
        ratio = (val - median) / median
        return max(0.0, 100.0 * (1.0 - ratio))

    # --- Trailing P/E -----------------------------------------------------
    components.append(_Component(
        "pe", micro.trailing_pe,
        _multiple_vs_median(micro.trailing_pe, sector_pe),
        0.22,
    ))

    # --- Forward P/E ------------------------------------------------------
    components.append(_Component(
        "forward_pe", micro.forward_pe,
        _multiple_vs_median(micro.forward_pe, sector_pe),
        0.10,
    ))

    # --- PEG (prefer trailing if available; fallback to plain peg) -------
    peg = micro.trailing_peg_ratio if _is_finite(micro.trailing_peg_ratio) else micro.peg_ratio
    components.append(_Component(
        "peg", peg,
        _ramp3(peg, full=1.0, half=2.0, zero=3.0)
        if _is_finite(peg) and peg is not None and peg > 0 else None,
        0.18,
    ))

    # --- P/B -------------------------------------------------------------
    components.append(_Component(
        "pb", micro.price_to_book,
        _multiple_vs_median(micro.price_to_book, sector_pb),
        0.10,
    ))

    # --- P/S -------------------------------------------------------------
    components.append(_Component(
        "ps", micro.price_to_sales,
        _ramp3(micro.price_to_sales, full=2.0, half=5.0, zero=10.0)
        if _is_finite(micro.price_to_sales) and micro.price_to_sales is not None
        and micro.price_to_sales > 0 else None,
        0.08,
    ))

    # --- EV/EBITDA -------------------------------------------------------
    components.append(_Component(
        "ev_ebitda", micro.enterprise_to_ebitda,
        _ramp3(micro.enterprise_to_ebitda, full=8.0, half=14.0, zero=25.0)
        if _is_finite(micro.enterprise_to_ebitda) and micro.enterprise_to_ebitda is not None
        and micro.enterprise_to_ebitda > 0 else None,
        0.10,
    ))

    # --- EV/Revenue ------------------------------------------------------
    components.append(_Component(
        "ev_revenue", micro.enterprise_to_revenue,
        _ramp3(micro.enterprise_to_revenue, full=2.0, half=5.0, zero=10.0)
        if _is_finite(micro.enterprise_to_revenue) and micro.enterprise_to_revenue is not None
        and micro.enterprise_to_revenue > 0 else None,
        0.05,
    ))

    # --- Dividend yield --------------------------------------------------
    # yfinance is inconsistent: <1 → fraction, >=1 → percent.
    dy_raw = micro.dividend_yield
    dy_score: float | None = None
    dy_pct: float | None = None
    if _is_finite(dy_raw) and dy_raw is not None and dy_raw >= 0:
        dy_pct = dy_raw if dy_raw > 1 else dy_raw * 100.0
        dy_score = _ramp(dy_pct, full=3.0, zero=0.0)
    components.append(_Component("dividend_yield", dy_pct, dy_score, 0.10))

    # --- Payout ratio sanity ---------------------------------------------
    # Healthy = 30-60%. Above 100% (over-paying earnings) → 0. 0% only
    # informative for dividend stocks; for growth stocks the dividend_yield
    # component already neutralises (None). Skip when there's no dividend.
    pr = micro.payout_ratio
    pr_score: float | None = None
    if _is_finite(pr) and pr is not None and (dy_pct is not None and dy_pct > 0):
        if pr <= 0:
            pr_score = 0.0
        elif pr <= 0.30:
            pr_score = 70.0   # low but healthy
        elif pr <= 0.60:
            pr_score = 100.0  # sweet spot
        elif pr <= 1.0:
            pr_score = max(0.0, 100.0 * (1.0 - (pr - 0.60) / 0.40))
        else:
            pr_score = 0.0    # paying out more than it earns
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

    q_score, _, q_break = _quality(stock, micro, sector_stats)
    g_score, _, g_break = _growth(stock, fundamentals, sector_stats)
    v_score, _, v_break = _value(stock, micro, last_close, sector_stats)
    m_score, _, m_break = _momentum(stock, micro, closes, ohlcv_df)
    s_score, _, s_break = _sentiment(
        stock, fundamentals, last_close,
        news_polarity=news_polarity, news_count=news_count,
    )

    sub: dict[str, float | None] = {
        "quality": q_score,
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
        "quality": q_break,
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
        quality=cs.sub_scores["quality"],
        growth=cs.sub_scores["growth"],
        value=cs.sub_scores["value"],
        momentum=cs.sub_scores["momentum"],
        sentiment=cs.sub_scores["sentiment"],
        risk_tier=cs.risk_tier,
        computed_at=cs.computed_at,
        breakdown=json.dumps(cs.breakdown, allow_nan=False),
    )


def _build_sector_stats(stocks: list[Stock]) -> SectorStatsBundle:
    """Pre-pass: pull cached fundamentals once per ticker, group by
    sector, hand off to sector_stats_service.compute().

    Catalog has duplicate ticker rows (see CLAUDE.md) — we dedupe by
    ticker so a stock with two rows doesn't double-weight in its
    sector's median. Fundamentals fetch failures are silent: a stock
    with no fundamentals just doesn't contribute to any aggregate.
    """
    by_sector: dict[str, list[Fundamentals]] = {}
    seen_tickers: set[str] = set()
    for stock in stocks:
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


def recompute_all(db: Session) -> int:
    """Batch UPSERT scores for every stock. Returns count successfully scored.

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
    """
    stocks = db.execute(select(Stock)).scalars().all()

    # Pre-pass: build sector_stats once per recompute run. Cost is
    # negligible (fundamentals come from L1/L2 cache for ~889 tickers,
    # ~50ms total) and amortises across the entire score loop.
    sector_stats = _build_sector_stats(list(stocks))

    seen_ids: set[int] = set()
    ok = 0
    failed = 0

    for stock in stocks:
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

    if failed:
        logger.info(f"[score] recompute_all: ok={ok} failed={failed}")
    else:
        logger.info(f"[score] recompute_all: ok={ok}")
    return ok
