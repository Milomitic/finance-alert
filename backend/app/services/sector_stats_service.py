"""Sector-level fundamental medians (P/E, P/B, ROE, growth, margins, etc).

Computed once per `recompute_all` and injected into the per-stock
scoring pipeline so each stock's value/quality/growth pillars can be
benchmarked against its **actual** sector peers in our universe -
rather than the static V1 hardcoded medians (`_SECTOR_PE_MEDIAN`,
`_SECTOR_PB_MEDIAN`) which never adapt to market regime shifts.

Why medians, not means?
-----------------------
A single ticker with P/E = 900 (loss-making turnaround story) would
swing a sector mean wildly; the median is robust by construction.
For consistency every aggregate here is a median.

Why a min-N gate per sector?
----------------------------
A "sector" with 1-2 tickers (e.g. obscure GICS subset, or just thin
catalog coverage of `Real Estate`) gives a degenerate "median" that's
basically the single value itself - providing zero benchmarking
signal. We require >=4 tickers with a present value before publishing
a sector-level stat; otherwise the consumer falls back to the
hardcoded baseline (V1 behavior).

Why not persist to a DB table?
------------------------------
Sector stats live in process memory tied to one `recompute_all` call.
The score breakdown JSON already records which median was used, so
historical reproducibility doesn't need a separate table. The API
endpoint `/api/sectors/{name}/detail` recomputes from current `Stock`
+ fundamentals on the fly - fast (~889 stocks * ~5 lookups < 50ms).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.stock_fundamentals_service import Fundamentals


# Minimum number of tickers in a sector before we publish stats for it.
# Below this we let consumers fall back to the universe-wide hardcoded
# baseline - averaging 1-3 values produces a "median" that's basically
# noise.
_MIN_TICKERS_PER_SECTOR = 4


def _is_finite(x: object) -> bool:
    if x is None:
        return False
    try:
        f = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def _normalise_div_yield(v: float | None) -> float | None:
    """yfinance dividend_yield is inconsistent: <1 -> fraction (0.0231),
    >=1 -> percent (2.31). Normalise to PERCENT at intake."""
    if v is None or not _is_finite(v) or v < 0:
        return None
    return v if v > 1 else v * 100.0


def _safe_median(values: list[float]) -> float | None:
    """Median of finite-positive values; None when fewer than the min."""
    finite = [float(v) for v in values if _is_finite(v) and float(v) > 0]
    if len(finite) < _MIN_TICKERS_PER_SECTOR:
        return None
    return statistics.median(finite)


def _signed_median(values: list[float]) -> float | None:
    """Median allowing negative values (growth, margins). Same N gate."""
    finite = [float(v) for v in values if _is_finite(v)]
    if len(finite) < _MIN_TICKERS_PER_SECTOR:
        return None
    return statistics.median(finite)


@dataclass
class SectorStats:
    """Median snapshot of one sector's fundamentals.

    Each field is `None` when fewer than `_MIN_TICKERS_PER_SECTOR`
    members of the sector reported a finite value for it. The scoring
    consumer falls back to the V1 hardcoded baseline in that case.
    """
    sector: str
    n: int  # member count (regardless of which fields are populated)

    # "Lower is better" multiples (Value pillar)
    pe_median: float | None = None
    forward_pe_median: float | None = None
    pb_median: float | None = None
    ps_median: float | None = None
    ev_ebitda_median: float | None = None
    ev_revenue_median: float | None = None
    peg_median: float | None = None

    # "Higher is better" quality (fractions, e.g. 0.18 = 18%)
    roe_median: float | None = None
    roa_median: float | None = None
    profit_margin_median: float | None = None
    operating_margin_median: float | None = None
    gross_margin_median: float | None = None
    current_ratio_median: float | None = None  # ratio (higher is better)
    quick_ratio_median: float | None = None    # ratio
    debt_equity_median: float | None = None    # yfinance reports as percent

    # "Higher is better" growth (signed fractions — can go negative)
    revenue_growth_median: float | None = None
    earnings_growth_median: float | None = None
    earnings_quarterly_growth_median: float | None = None
    revenue_quarterly_growth_median: float | None = None
    earnings_growth_5y_median: float | None = None
    revenue_growth_5y_median: float | None = None

    # Income
    dividend_yield_median: float | None = None  # PERCENT (normalised)

    # Sustainability extras (V3.2)
    fcf_to_ni_median: float | None = None        # FCF / Net Income ratio
    dividend_coverage_median: float | None = None  # EPS / DPS multiple


@dataclass
class SectorStatsBundle:
    """Per-sector dict + the universe-wide medians as a fallback layer.

    `.resolve(sector, "field")` returns the sector's median if present,
    else the universe median if present, else None - so callers get a
    single-line lookup with built-in two-tier fallback.
    """
    by_sector: dict[str, SectorStats] = field(default_factory=dict)
    universe: SectorStats = field(default_factory=lambda: SectorStats(sector="_universe", n=0))

    def for_sector(self, name: str | None) -> SectorStats | None:
        """Return the sector's row if it exists, else the universe row."""
        if name and name in self.by_sector:
            return self.by_sector[name]
        return self.universe if self.universe.n > 0 else None

    def resolve(self, name: str | None, field_name: str) -> float | None:
        """Look up `field_name` for sector `name`, falling through to
        the universe row when the sector value is missing/None."""
        sec = self.by_sector.get(name or "")
        if sec is not None:
            v = getattr(sec, field_name, None)
            if v is not None:
                return v
        return getattr(self.universe, field_name, None)


def compute(fundamentals_by_sector: dict[str, list[Fundamentals]]) -> SectorStatsBundle:
    """Aggregate medians over all sectors + the full universe.

    Stocks with sector = None / empty are silently fed into the
    universe row but skipped from the by-sector dict - they'd produce
    a meaningless "(empty)" sector entry in UIs.
    """
    bundle = SectorStatsBundle()
    all_funds: list[Fundamentals] = []

    for sector_name, funds in fundamentals_by_sector.items():
        all_funds.extend(funds)
        if not sector_name:
            continue
        bundle.by_sector[sector_name] = _compute_one(sector_name, funds)

    bundle.universe = _compute_one("_universe", all_funds)
    return bundle


def _compute_one(sector: str, funds: list[Fundamentals]) -> SectorStats:
    """Build a SectorStats from a list of fundamentals."""
    micros = [f.micro for f in funds if f and f.micro is not None]

    return SectorStats(
        sector=sector,
        n=len(funds),
        # Multiples (lower better)
        pe_median=_safe_median([m.trailing_pe for m in micros if m.trailing_pe is not None]),
        forward_pe_median=_safe_median(
            [m.forward_pe for m in micros if m.forward_pe is not None]
        ),
        pb_median=_safe_median([m.price_to_book for m in micros if m.price_to_book is not None]),
        ps_median=_safe_median(
            [m.price_to_sales for m in micros if m.price_to_sales is not None]
        ),
        ev_ebitda_median=_safe_median(
            [m.enterprise_to_ebitda for m in micros if m.enterprise_to_ebitda is not None]
        ),
        ev_revenue_median=_safe_median(
            [m.enterprise_to_revenue for m in micros if m.enterprise_to_revenue is not None]
        ),
        peg_median=_safe_median([
            (m.trailing_peg_ratio if _is_finite(m.trailing_peg_ratio) else m.peg_ratio)
            for m in micros
            if (m.trailing_peg_ratio is not None or m.peg_ratio is not None)
        ]),
        # Quality (signed because some firms report negative ROE/margins)
        roe_median=_signed_median(
            [m.return_on_equity for m in micros if m.return_on_equity is not None]
        ),
        roa_median=_signed_median(
            [m.return_on_assets for m in micros if m.return_on_assets is not None]
        ),
        profit_margin_median=_signed_median(
            [m.profit_margins for m in micros if m.profit_margins is not None]
        ),
        operating_margin_median=_signed_median(
            [m.operating_margins for m in micros if m.operating_margins is not None]
        ),
        gross_margin_median=_signed_median(
            [m.gross_margins for m in micros if m.gross_margins is not None]
        ),
        current_ratio_median=_safe_median(
            [m.current_ratio for m in micros if m.current_ratio is not None]
        ),
        quick_ratio_median=_safe_median(
            [m.quick_ratio for m in micros if m.quick_ratio is not None]
        ),
        debt_equity_median=_safe_median(
            [m.debt_to_equity for m in micros if m.debt_to_equity is not None]
        ),
        # Growth (signed)
        revenue_growth_median=_signed_median(
            [m.revenue_growth for m in micros if m.revenue_growth is not None]
        ),
        earnings_growth_median=_signed_median(
            [m.earnings_growth for m in micros if m.earnings_growth is not None]
        ),
        earnings_quarterly_growth_median=_signed_median(
            [m.earnings_quarterly_growth for m in micros if m.earnings_quarterly_growth is not None]
        ),
        revenue_quarterly_growth_median=_signed_median(
            [m.revenue_quarterly_growth for m in micros if m.revenue_quarterly_growth is not None]
        ),
        earnings_growth_5y_median=_signed_median(
            [m.earnings_growth_5y for m in micros if m.earnings_growth_5y is not None]
        ),
        revenue_growth_5y_median=_signed_median(
            [m.revenue_growth_5y for m in micros if m.revenue_growth_5y is not None]
        ),
        # Income
        dividend_yield_median=_safe_median(
            [
                normalised
                for m in micros
                for normalised in [_normalise_div_yield(m.dividend_yield)]
                if normalised is not None
            ]
        ),
        # FCF / Net Income median: pull NI from MicroData.net_income_to_common
        # (Yahoo info dict, TTM). When that's missing, fall back to the
        # latest annual net_income from the AnnualPoint history.
        fcf_to_ni_median=_safe_median([
            ratio for ratio in (
                _fcf_to_ni_for_funds(f) for f in funds if f is not None
            ) if ratio is not None
        ]),
        # Dividend coverage = EPS_TTM / annual DPS
        dividend_coverage_median=_safe_median([
            cov for cov in (
                _dividend_coverage_for_micro(f.micro) for f in funds
                if f is not None and f.micro is not None
            ) if cov is not None
        ]),
    )



def _fcf_to_ni_for_funds(fundamentals) -> float | None:
    """Mirror of score_service._fcf_to_ni_ratio for sector aggregation.
    Kept as a private helper here to avoid a circular import (score_service
    imports sector_stats_service, not the other way around)."""
    if fundamentals is None or fundamentals.micro is None:
        return None
    micro = fundamentals.micro
    fcf = getattr(micro, "free_cashflow", None)
    if not _is_finite(fcf):
        return None
    ni = None
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


def _dividend_coverage_for_micro(micro) -> float | None:
    """Mirror of score_service._dividend_coverage."""
    eps = getattr(micro, "eps_trailing", None)
    div_rate = getattr(micro, "dividend_rate", None)
    if not _is_finite(eps) or not _is_finite(div_rate):
        return None
    if div_rate is None or float(div_rate) <= 0:
        return None
    if eps is None or float(eps) <= 0:
        return 0.0
    return float(eps) / float(div_rate)
