"""The 5 fundamental pillars of the Qualità composite: profitability,
sustainability, growth, value, sentiment — plus their lane helpers and the
V3.1 `_quality` back-compat shim.

NOTE (B4-9): the dead `_momentum()` pillar was DELETED here. It had been
retained-but-unused since the 3-lens cleanup (2026-05) removed the Momentum
pillar from the composite — price-action lives in TechnicalScore. The
`app.indicators` imports (ema/rsi/macd/bb/adx) went with it: no pillar in
the pure-fundamental composite reads indicators.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import Stock
from app.services import stock_news_service
from app.services.news_sentiment import classify_title
from app.services.score_service.common import (
    _aggregate,
    _blended_hib,
    _blended_lib,
    _blended_lib_multiple,
    _Component,
    _is_finite,
    _ramp,
    _ramp3,
    _resolve_med,
)
from app.services.sector_stats_service import SectorStatsBundle
from app.services.stock_fundamentals_service import (
    Fundamentals,
    MicroData,
)

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

    Components (weights add to 1.0). Weights re-tuned 2026-05 against
    point-in-time IC (SEC companyfacts, US universe 2016-2026; see
    app/scripts/entry_ic_report.py --validate-prof-retune). The prior
    weights loaded heavily on margin LEVELS (net 0.24, operating 0.18),
    which the IC study found flat-to-NEGATIVE at long horizons
    (net_margin -0.047 @252d) — making the OLD pillar counter-
    predictive at 1y (IC -0.009). The validated re-tune promotes the
    signals that DO predict (gross_margin +0.030, roa +0.020) and
    demotes the counter-predictive levels, flipping the 1y IC positive
    (+0.003) and improving it at every horizon.
      - Gross margin              (0.30)  best fundamental signal; durable moat
      - ROA                       (0.26)  validated, stable across horizons
      - ROE                       (0.18)  weakly positive
      - Profit (net) margin       (0.14)  level flat/neg long-horizon → demoted
      - Operating margin          (0.12)  level negative long-horizon → demoted
      - Insider holdings          (0.0)   informational only (QW1)
      - Institutional holdings    (0.0)   informational only (QW1)
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
        0.18,  # IC-retune: 0.26→0.18 (roe only weakly predictive, +0.010)
        sector_median=_med("roe_median"),
    ))
    components.append(_Component(
        "roa", micro.return_on_assets,
        _blended_hib(micro.return_on_assets, _med("roa_median"),
                     abs_full=0.10, abs_half=0.05, abs_zero=0.0,
                     rel_full_pp=0.025),
        0.26,  # IC-retune: 0.18→0.26 (roa validated +0.020, stable)
        sector_median=_med("roa_median"),
    ))
    components.append(_Component(
        "profit_margin", micro.profit_margins,
        _blended_hib(micro.profit_margins, _med("profit_margin_median"),
                     abs_full=0.20, abs_half=0.10, abs_zero=0.0,
                     rel_full_pp=0.05),
        0.14,  # IC-retune: 0.24→0.14 (net-margin LEVEL -0.047 @252d;
               # kept non-zero as a "profitable at all" quality floor)
        sector_median=_med("profit_margin_median"),
    ))
    components.append(_Component(
        "operating_margin", micro.operating_margins,
        _blended_hib(micro.operating_margins, _med("operating_margin_median"),
                     abs_full=0.20, abs_half=0.10, abs_zero=0.0,
                     rel_full_pp=0.05),
        0.12,  # IC-retune: 0.18→0.12 (operating-margin level -0.037 @252d)
        sector_median=_med("operating_margin_median"),
    ))
    components.append(_Component(
        "gross_margin", micro.gross_margins,
        _blended_hib(micro.gross_margins, _med("gross_margin_median"),
                     abs_full=0.50, abs_half=0.30, abs_zero=0.10,
                     rel_full_pp=0.10),
        0.30,  # IC-retune: 0.14→0.30 (best fundamental signal, +0.030
               # consistent across horizons); sum=1.00
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
    from dataclasses import dataclass
    from dataclasses import field as _field

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

    # --- Revenue & earnings growth (sector-aware blend) -------------------
    # NOTE: micro.revenue_growth / micro.earnings_growth now carry the
    # CURRENT-FY PROJECTED growth (analyst-estimate-inclusive: reported
    # quarters + consensus for the not-yet-reported quarters vs prior-FY
    # actual) when available, falling back to trailing YoY only when the
    # projection is absent. The sector medians are aggregated from the same
    # fields, so this stays apples-to-apples. See stock_fundamentals_service
    # `_fetch_fresh` (prefer-the-projection block) for where the swap happens.
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
        0.06,  # M1: 0.10→0.06 — single-quarter EPS growth is the
               # noisiest, most YoY-redundant lane (collinear cluster);
               # weight shifted to the orthogonal beats + persistent 5Y.
    sector_median=_med("earnings_quarterly_growth_median"),
    ))
    qrg = micro.revenue_quarterly_growth if micro else None
    components.append(_Component(
        "qoq_revenue_growth", qrg,
        _blended_hib(qrg, _med("revenue_quarterly_growth_median"),
                     abs_full=0.10, abs_half=0.0, abs_zero=-0.06,
                     rel_full_pp=0.05),
        0.05,  # M1: 0.08→0.05 — same collinear-QoQ rationale.
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
        components.append(_Component("earnings_beats", beats, beat_score, 0.15))  # M1: 0.12→0.15 (PEAD = most orthogonal growth-adjacent signal)
    else:
        components.append(_Component("earnings_beats", None, None, 0.15))

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
        0.15,  # M1: 0.13→0.15 — multi-year persistence > single quarter.
    sector_median=_med("revenue_growth_5y_median"),
    ))
    e5 = micro.earnings_growth_5y if micro else None
    components.append(_Component(
        "earnings_growth_5y", e5,
        _blended_hib(e5, _med("earnings_growth_5y_median"),
                     abs_full=0.15, abs_half=0.05, abs_zero=-0.05,
                     rel_full_pp=0.04),
        0.15,  # M1: 0.13→0.15 — multi-year persistence > single quarter.
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
