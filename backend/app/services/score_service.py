"""Composite stock-scoring service.

Per-stock 0-100 score from 5 sub-scores: Quality, Growth, Value, Momentum,
Sentiment. Each sub-score is itself a 0-100 weighted bag of components mapped
through piecewise-linear ramps (full points → half points → zero) so the
output reflects "good / not good" rather than ranking by raw magnitude.

NULL sub-scores (missing data) are excluded and remaining weights re-normalised
so a stock with no analyst coverage still scores out of 100 from the other
four pillars.

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

from app.indicators.macd import macd as macd_indicator
from app.indicators.rsi import rsi as rsi_indicator
from app.models import OhlcvDaily, Stock, StockScore
from app.services import stock_fundamentals_service, stock_news_service
from app.services.stock_fundamentals_service import (
    Fundamentals,
    MicroData,
)


# ---------------------------------------------------------------------------
# Pillar weights and risk tier thresholds.
# ---------------------------------------------------------------------------

PILLAR_WEIGHTS: dict[str, float] = {
    "quality": 0.25,
    "growth": 0.25,
    "value": 0.15,
    "momentum": 0.20,
    "sentiment": 0.15,
}

RISK_TIERS: tuple[str, ...] = ("conservative", "moderate", "aggressive")

# Static V1 sector P/E medians. Hardcoded — V2 may compute these per-period
# from the universe. Universe-wide fallback is ~22 (rough S&P long-term TTM).
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

# Defensive/cyclical sectors for the risk classifier (Beta + vol + sector).
_DEFENSIVE_SECTORS = {
    "Utilities", "Consumer Defensive", "Consumer Staples",
    "Healthcare", "Health Care",
}
_CYCLICAL_SECTORS = {
    "Technology", "Consumer Cyclical", "Consumer Discretionary",
    "Energy", "Basic Materials", "Materials",
}

# Mega-cap threshold — > $200B shifts risk down one tier (per design doc).
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


def _ramp(value: float, points_max: float, *, full: float, zero: float) -> float:
    """Piecewise-linear ramp: 0 at `zero`, points_max at `full`, linear between.

    Works in both directions (full > zero gives a "higher is better" ramp;
    full < zero gives "lower is better"). Values are clamped to [0, points_max].
    """
    if full == zero:
        return points_max if value == full else 0.0
    if full > zero:
        if value >= full:
            return points_max
        if value <= zero:
            return 0.0
        return points_max * (value - zero) / (full - zero)
    # full < zero: lower-is-better
    if value <= full:
        return points_max
    if value >= zero:
        return 0.0
    return points_max * (zero - value) / (zero - full)


def _ramp3(value: float, points_max: float, *, full: float, half: float, zero: float) -> float:
    """Three-point piecewise-linear ramp: full / half / zero.

    Two segments: zero-to-half maps to [0, max/2], half-to-full maps to
    [max/2, max]. Values outside [zero, full] (or [full, zero] for inverted
    ramps) clamp to the endpoint.
    """
    half_pts = points_max / 2.0
    # Detect orientation via outer endpoints.
    higher_is_better = full > zero
    if higher_is_better:
        if value >= full:
            return points_max
        if value <= zero:
            return 0.0
        if value >= half:
            return half_pts + (points_max - half_pts) * (value - half) / (full - half)
        return half_pts * (value - zero) / (half - zero)
    # lower-is-better
    if value <= full:
        return points_max
    if value >= zero:
        return 0.0
    if value <= half:
        return half_pts + (points_max - half_pts) * (half - value) / (half - full)
    return half_pts * (zero - value) / (zero - half)


def _safe_round(x: float, digits: int = 2) -> float:
    """Round to `digits`, clamping non-finite to 0.0 — JSON cannot serialise NaN/Inf."""
    if not _is_finite(x):
        return 0.0
    return round(float(x), digits)


def _component(raw: Any, points: float, max_pts: float) -> dict[str, Any]:
    """Build a per-component breakdown dict.

    `raw` may be None when the input was unavailable; the UI uses that to
    render a "—" instead of a bar. Points and max are always present so the
    UI can compute the partial-fill percentage.
    """
    if raw is not None and not _is_finite(raw):
        raw_out: float | None = None
    elif raw is None:
        raw_out = None
    else:
        raw_out = _safe_round(raw, 4)
    return {"raw": raw_out, "points": _safe_round(points, 2), "max": _safe_round(max_pts, 2)}


# ---------------------------------------------------------------------------
# Sub-score computation. Each function returns (points, max, breakdown).
# `points` and `max` already account for missing-data penalties — we award
# zero for any component whose input is None (rather than dropping the
# component) so the per-stock max is always 100. Stocks with no usable inputs
# at all return (0.0, 0.0, {}) which signals "exclude this pillar".
# ---------------------------------------------------------------------------

def _quality(stock: Stock, micro: MicroData | None) -> tuple[float, float, dict]:
    if micro is None:
        return 0.0, 0.0, {}
    breakdown: dict[str, Any] = {}
    total = 0.0
    any_input = False

    # ROE: full @ 20%, half @ 10%, zero @ 0% (yfinance returns fractions).
    roe = micro.return_on_equity
    if _is_finite(roe):
        any_input = True
        pts = _ramp3(roe, 30.0, full=0.20, half=0.10, zero=0.0)
        breakdown["roe"] = _component(roe, pts, 30.0)
        total += pts
    else:
        breakdown["roe"] = _component(None, 0.0, 30.0)

    # Profit margin: full @ 20%, half @ 10%, zero @ 0%.
    pm = micro.profit_margins
    if _is_finite(pm):
        any_input = True
        pts = _ramp3(pm, 25.0, full=0.20, half=0.10, zero=0.0)
        breakdown["profit_margin"] = _component(pm, pts, 25.0)
        total += pts
    else:
        breakdown["profit_margin"] = _component(None, 0.0, 25.0)

    # FCF: binary. Positive → full, non-positive (or missing) → 0.
    fcf = micro.free_cashflow
    if _is_finite(fcf):
        any_input = True
        pts = 20.0 if fcf > 0 else 0.0
        breakdown["fcf"] = _component(fcf, pts, 20.0)
        total += pts
    else:
        breakdown["fcf"] = _component(None, 0.0, 20.0)

    # Debt/Equity: yfinance returns this as percent (e.g. 145.2 means 1.45).
    # Spec: full @ ≤50%, half @ 100%, zero @ ≥200%.
    de = micro.debt_to_equity
    if _is_finite(de):
        any_input = True
        pts = _ramp3(de, 15.0, full=50.0, half=100.0, zero=200.0)
        breakdown["debt_equity"] = _component(de, pts, 15.0)
        total += pts
    else:
        breakdown["debt_equity"] = _component(None, 0.0, 15.0)

    # Current ratio: full @ 2, half @ 1, zero @ 0.7.
    cr = micro.current_ratio
    if _is_finite(cr):
        any_input = True
        pts = _ramp3(cr, 10.0, full=2.0, half=1.0, zero=0.7)
        breakdown["current_ratio"] = _component(cr, pts, 10.0)
        total += pts
    else:
        breakdown["current_ratio"] = _component(None, 0.0, 10.0)

    if not any_input:
        return 0.0, 0.0, {}
    return total, 100.0, breakdown


def _growth(stock: Stock, fundamentals: Fundamentals | None) -> tuple[float, float, dict]:
    if fundamentals is None:
        return 0.0, 0.0, {}
    breakdown: dict[str, Any] = {}
    total = 0.0
    any_input = False
    micro = fundamentals.micro

    # Revenue growth (YoY): yfinance returns fraction. Full @ 20%, half @ 0%, zero @ -10%.
    rg = micro.revenue_growth if micro else None
    if _is_finite(rg):
        any_input = True
        pts = _ramp3(rg, 35.0, full=0.20, half=0.0, zero=-0.10)
        breakdown["revenue_growth"] = _component(rg, pts, 35.0)
        total += pts
    else:
        breakdown["revenue_growth"] = _component(None, 0.0, 35.0)

    # Earnings growth (YoY) — proxy for EPS growth.
    eg = micro.earnings_growth if micro else None
    if _is_finite(eg):
        any_input = True
        pts = _ramp3(eg, 35.0, full=0.20, half=0.0, zero=-0.10)
        breakdown["eps_growth"] = _component(eg, pts, 35.0)
        total += pts
    else:
        breakdown["eps_growth"] = _component(None, 0.0, 35.0)

    # Earnings beat ratio: count beats among last 4 reported quarters.
    # Beat = reported > estimate (both non-null).
    beats: int | None = None
    earnings = fundamentals.earnings or []
    last4 = [e for e in earnings if e.eps_reported is not None and e.eps_estimate is not None][-4:]
    if last4:
        beats = sum(1 for e in last4 if e.eps_reported > e.eps_estimate)
        any_input = True
        # 4/4 → full (30), 2/4 → half (15), 0/4 → 0. Linear in beats.
        pts = _ramp3(float(beats), 30.0, full=4.0, half=2.0, zero=0.0)
        breakdown["earnings_beat"] = {
            "raw": beats,
            "points": _safe_round(pts, 2),
            "max": 30.0,
            "out_of": len(last4),
        }
        total += pts
    else:
        breakdown["earnings_beat"] = {"raw": None, "points": 0.0, "max": 30.0, "out_of": 0}

    if not any_input:
        return 0.0, 0.0, {}
    return total, 100.0, breakdown


def _value(stock: Stock, micro: MicroData | None, last_close: float | None) -> tuple[float, float, dict]:
    """Note: `last_close` only used to derive the dividend yield fallback when
    yfinance's dividendYield field is missing (rare — most equities have it)."""
    if micro is None:
        return 0.0, 0.0, {}
    breakdown: dict[str, Any] = {}
    total = 0.0
    any_input = False

    # P/E (TTM) vs sector median. Below median → full points, scales down above.
    sector_median = _SECTOR_PE_MEDIAN.get(stock.sector or "", _UNIVERSE_PE_MEDIAN)
    pe = micro.trailing_pe
    # Negative TTM PE (loss) → 0 points; that's a signal of quality issues, not value.
    if _is_finite(pe) and pe is not None and pe > 0:
        any_input = True
        # Full at sector_median or below; scale down so 2x median gives 0.
        # Maps the raw P/E to a 0-40 band centred on sector_median.
        if pe <= sector_median:
            pts = 40.0
        else:
            # Linear: pe = median → 40, pe = 2 * median → 0.
            ratio = (pe - sector_median) / sector_median  # 0 at median, 1 at 2× median
            pts = max(0.0, 40.0 * (1.0 - ratio))
        breakdown["pe"] = {
            **_component(pe, pts, 40.0),
            "sector_median": sector_median,
        }
        total += pts
    else:
        breakdown["pe"] = {
            "raw": pe if _is_finite(pe) else None,
            "points": 0.0,
            "max": 40.0,
            "sector_median": sector_median,
        }

    # PEG: full @ ≤1, half @ 2, zero @ ≥3.
    peg = micro.peg_ratio
    if _is_finite(peg) and peg is not None and peg > 0:
        any_input = True
        pts = _ramp3(peg, 30.0, full=1.0, half=2.0, zero=3.0)
        breakdown["peg"] = _component(peg, pts, 30.0)
        total += pts
    else:
        breakdown["peg"] = _component(None if not _is_finite(peg) else peg, 0.0, 30.0)

    # Dividend yield: full @ ≥3%, zero @ 0%. Linear.
    # yfinance's `dividendYield` is sometimes a fraction (0.025) and sometimes a
    # percent (2.5) depending on version. Detect by magnitude: if > 1, treat as %.
    dy_raw = micro.dividend_yield
    if _is_finite(dy_raw) and dy_raw is not None and dy_raw >= 0:
        any_input = True
        dy_pct = dy_raw if dy_raw > 1 else dy_raw * 100.0
        pts = _ramp(dy_pct, 30.0, full=3.0, zero=0.0)
        breakdown["dividend_yield"] = _component(dy_pct, pts, 30.0)
        total += pts
    else:
        breakdown["dividend_yield"] = _component(None, 0.0, 30.0)

    if not any_input:
        return 0.0, 0.0, {}
    return total, 100.0, breakdown


def _momentum(
    stock: Stock,
    micro: MicroData | None,
    closes: pd.Series | None,
) -> tuple[float, float, dict]:
    """closes: ascending pandas Series of close prices (≥ 30 bars ideal)."""
    breakdown: dict[str, Any] = {}
    total = 0.0
    any_input = False

    # 52-week change: prefer micro.fifty_two_week_change (yfinance fraction);
    # else compute from closes if we have ≥ 252 bars.
    chg_52w: float | None = None
    if micro is not None and _is_finite(micro.fifty_two_week_change):
        chg_52w = float(micro.fifty_two_week_change)  # already a fraction
    elif closes is not None and len(closes) >= 252:
        ref = float(closes.iloc[-252])
        if ref > 0:
            chg_52w = (float(closes.iloc[-1]) - ref) / ref
    if chg_52w is not None and _is_finite(chg_52w):
        any_input = True
        # Full @ ≥50%, half @ 0%, zero @ -30%.
        pts = _ramp3(chg_52w, 30.0, full=0.50, half=0.0, zero=-0.30)
        breakdown["change_52w"] = _component(chg_52w, pts, 30.0)
        total += pts
    else:
        breakdown["change_52w"] = _component(None, 0.0, 30.0)

    # RSI(14) from closes.
    rsi_val: float | None = None
    if closes is not None and len(closes) >= 15:
        try:
            rsi_series = rsi_indicator(closes, 14)
            last = rsi_series.iloc[-1]
            if pd.notna(last):
                rsi_val = float(last)
        except Exception:  # noqa: BLE001
            rsi_val = None
    if rsi_val is not None and _is_finite(rsi_val):
        any_input = True
        # Spec: 30-70 → 50% (10 pts); < 30 (oversold) → 80% (16 pts);
        # > 70 (overbought) → 20% (4 pts). Step function.
        if rsi_val < 30:
            pts = 16.0
        elif rsi_val > 70:
            pts = 4.0
        else:
            pts = 10.0
        breakdown["rsi"] = _component(rsi_val, pts, 20.0)
        total += pts
    else:
        breakdown["rsi"] = _component(None, 0.0, 20.0)

    # MACD: line > signal AND hist > 0 → full; else 0.
    macd_pts = 0.0
    macd_state: str | None = None
    if closes is not None and len(closes) >= 35:
        try:
            line, sig, hist = macd_indicator(closes, fast=12, slow=26, signal=9)
            line_v = float(line.iloc[-1]) if pd.notna(line.iloc[-1]) else None
            sig_v = float(sig.iloc[-1]) if pd.notna(sig.iloc[-1]) else None
            hist_v = float(hist.iloc[-1]) if pd.notna(hist.iloc[-1]) else None
            if line_v is not None and sig_v is not None and hist_v is not None:
                any_input = True
                if line_v > sig_v and hist_v > 0:
                    macd_pts = 20.0
                    macd_state = "bullish"
                else:
                    macd_state = "bearish_or_flat"
                breakdown["macd"] = {
                    "raw": _safe_round(hist_v, 4),
                    "points": macd_pts,
                    "max": 20.0,
                    "state": macd_state,
                }
                total += macd_pts
            else:
                breakdown["macd"] = _component(None, 0.0, 20.0)
        except Exception:  # noqa: BLE001
            breakdown["macd"] = _component(None, 0.0, 20.0)
    else:
        breakdown["macd"] = _component(None, 0.0, 20.0)

    # 30-day momentum (≈ 21 trading days).
    mom30: float | None = None
    if closes is not None and len(closes) >= 22:
        ref = float(closes.iloc[-22])
        if ref > 0:
            mom30 = (float(closes.iloc[-1]) - ref) / ref
    if mom30 is not None and _is_finite(mom30):
        any_input = True
        pts = _ramp3(mom30, 30.0, full=0.10, half=0.0, zero=-0.10)
        breakdown["momentum_30d"] = _component(mom30, pts, 30.0)
        total += pts
    else:
        breakdown["momentum_30d"] = _component(None, 0.0, 30.0)

    if not any_input:
        return 0.0, 0.0, {}
    return total, 100.0, breakdown


def _net_upgrades_90d(fundamentals: Fundamentals) -> int | None:
    """Count net upgrades − downgrades from analyst_actions over the last 90 days.

    Uses the `action` code from yfinance: "up" / "down" / "main" / "init" / "reit".
    Returns None if no actions are available (so the component is treated as
    missing rather than a definitive zero).
    """
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
        # "main", "init", "reit" — neutral
    return net if seen > 0 else None


def _sentiment(
    stock: Stock,
    fundamentals: Fundamentals | None,
    news_count: int | None,
    last_close: float | None,
) -> tuple[float, float, dict]:
    if fundamentals is None:
        return 0.0, 0.0, {}
    breakdown: dict[str, Any] = {}
    total = 0.0
    any_input = False

    # Analyst price-target upside: (mean_target - last_close) / last_close.
    pt_mean = fundamentals.price_target.mean if fundamentals.price_target else None
    upside: float | None = None
    if _is_finite(pt_mean) and _is_finite(last_close) and last_close and last_close > 0:
        upside = (float(pt_mean) - float(last_close)) / float(last_close)
    if upside is not None and _is_finite(upside):
        any_input = True
        # Full @ ≥20% upside, half @ 0%, zero @ -10%.
        pts = _ramp3(upside, 50.0, full=0.20, half=0.0, zero=-0.10)
        breakdown["price_target_upside"] = _component(upside, pts, 50.0)
        total += pts
    else:
        breakdown["price_target_upside"] = _component(None, 0.0, 50.0)

    # Net upgrades − downgrades (90d).
    net_up = _net_upgrades_90d(fundamentals)
    if net_up is not None:
        any_input = True
        # Full @ ≥+3, half @ 0, zero @ ≤-3. Linear.
        pts = _ramp3(float(net_up), 30.0, full=3.0, half=0.0, zero=-3.0)
        breakdown["net_upgrades_90d"] = {
            "raw": net_up,
            "points": _safe_round(pts, 2),
            "max": 30.0,
        }
        total += pts
    else:
        breakdown["net_upgrades_90d"] = {"raw": None, "points": 0.0, "max": 30.0}

    # News volume (last 30d). Linear from 0 → 20+ articles.
    if news_count is not None and news_count >= 0:
        any_input = True
        pts = _ramp(float(news_count), 20.0, full=20.0, zero=0.0)
        breakdown["news_volume"] = {
            "raw": int(news_count),
            "points": _safe_round(pts, 2),
            "max": 20.0,
        }
        total += pts
    else:
        breakdown["news_volume"] = {"raw": None, "points": 0.0, "max": 20.0}

    if not any_input:
        return 0.0, 0.0, {}
    return total, 100.0, breakdown


# ---------------------------------------------------------------------------
# Risk classification.
# ---------------------------------------------------------------------------

def _classify_risk(
    stock: Stock,
    micro: MicroData | None,
    volatility_90d: float | None,
) -> str:
    """Map (Beta, vol, sector, market_cap) → tier via summed +1/-1 votes.

    Each input contributes -1 (toward conservative), 0 (neutral), or +1
    (toward aggressive); votes are summed and thresholded.

    Spec (from docs/scoring-algorithm.md):
      - Beta < 0.8 → conservative; > 1.3 → aggressive
      - 90d vol < 1.5% → conservative; > 3% → aggressive
      - Defensive sectors → conservative; cyclical → aggressive
      - Market cap > $200B → shifts down one tier (subtracts 1)
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
        # volatility_90d here is in percent (e.g. 2.0 means 2%).
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
    if mc is not None and mc > _MEGA_CAP_THRESHOLD:
        score -= 1   # mega-cap → shift down one tier

    # Threshold: ≤ -1 → conservative, ≥ +1 → aggressive, else moderate.
    # If we had no inputs at all, default to moderate.
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
    """Return effective weights: zero for missing pillars, others sum to 1.

    Example: if sentiment is None, the remaining weights (0.25 + 0.25 + 0.15 + 0.20)
    sum to 0.85 — each gets divided by 0.85 so they sum to 1.0 again.
    """
    present = {k: PILLAR_WEIGHTS[k] for k, v in sub_scores.items() if v is not None}
    total = sum(present.values())
    if total <= 0:
        return {k: 0.0 for k in PILLAR_WEIGHTS}
    return {k: (present[k] / total if k in present else 0.0) for k in PILLAR_WEIGHTS}


def _compute_volatility_90d(closes: pd.Series | None) -> float | None:
    """90-day daily-return stdev as a percent (e.g. 2.0 means 2.0%/day).

    Needs ≥ 60 bars to be meaningful; returns None below that.
    """
    if closes is None or len(closes) < 60:
        return None
    window = closes.iloc[-90:] if len(closes) >= 90 else closes
    rets = window.pct_change().dropna()
    if rets.empty:
        return None
    std = float(rets.std())
    if not _is_finite(std):
        return None
    return std * 100.0  # convert fraction → percent


def _last_30d_news_count(ticker: str) -> int | None:
    """Count news items from the last 30 days. Returns None on fetch failure
    (so the sentiment component is treated as missing, not zero)."""
    try:
        items = stock_news_service.get_news(ticker, limit=50)
    except Exception:  # noqa: BLE001
        return None
    if not items:
        # An empty list could mean "no recent news" or "yfinance failed and
        # returned []". The service caches both as []; we treat empty as 0
        # rather than None — over-estimating "no news" is the safer call here.
        return 0
    today = datetime.now(UTC).date()
    count = 0
    for n in items:
        pub = n.get("published_at")
        if not pub:
            continue
        try:
            # ISO 8601 with optional trailing Z
            d = datetime.fromisoformat(pub.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if (today - d).days <= 30:
            count += 1
    return count


def _load_closes(db: Session, stock_id: int, limit: int = 260) -> pd.Series | None:
    """Ascending close-price series for a stock. None if no bars."""
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


# ---------------------------------------------------------------------------
# Public entry points.
# ---------------------------------------------------------------------------

@dataclass
class _ComputedScore:
    """Internal pre-persistence result. Caller decides whether to UPSERT."""
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
) -> _ComputedScore:
    """Pure compute path — no DB writes, no fundamentals fetch.

    Splitting this out makes tests trivial: stub the inputs, assert the result.
    The `compute_score(db, stock)` wrapper does the DB+network plumbing.
    """
    micro = fundamentals.micro if fundamentals is not None else None
    last_close = float(closes.iloc[-1]) if closes is not None and len(closes) > 0 else None

    q_pts, q_max, q_break = _quality(stock, micro)
    g_pts, g_max, g_break = _growth(stock, fundamentals)
    v_pts, v_max, v_break = _value(stock, micro, last_close)
    m_pts, m_max, m_break = _momentum(stock, micro, closes)
    s_pts, s_max, s_break = _sentiment(stock, fundamentals, news_count, last_close)

    def _norm(pts: float, mx: float) -> float | None:
        if mx <= 0:
            return None
        return _safe_round(pts / mx * 100.0, 2)

    sub = {
        "quality": _norm(q_pts, q_max),
        "growth": _norm(g_pts, g_max),
        "value": _norm(v_pts, v_max),
        "momentum": _norm(m_pts, m_max),
        "sentiment": _norm(s_pts, s_max),
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


def compute_score(db: Session, stock: Stock) -> StockScore:
    """Compute a fresh StockScore for one stock. NOT persisted by this call.

    Pulls fundamentals from the cache (no network if fresh), recent OHLCV from
    the DB, and a news count via the news-service cache. The caller is expected
    to UPSERT — see `recompute_all` for the batch path.
    """
    try:
        fundamentals = stock_fundamentals_service.get_fundamentals(stock.ticker)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[score] fundamentals fetch failed for {stock.ticker}: {exc}")
        fundamentals = None
    closes = _load_closes(db, stock.id)
    news_count = _last_30d_news_count(stock.ticker)

    cs = _build_score(stock, fundamentals, closes, news_count)
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


def recompute_all(db: Session) -> int:
    """Batch UPSERT scores for every stock. Returns count successfully scored.

    One transaction. Uses the fundamentals + news caches (no extra network if
    they're warm). Does NOT raise on per-stock failure — logs and continues.
    """
    stocks = db.execute(select(Stock)).scalars().all()
    # Catalog has duplicate ticker rows (see CLAUDE.md). Dedupe by ticker so we
    # don't attempt to write two StockScore rows for "the same" logical stock —
    # the second write would raise IntegrityError on the PK if both stock_ids
    # somehow collided. In practice each Stock row has a distinct id so we can
    # score every row, but we keep the dedupe on (stock.id) as a safety net.
    seen_ids: set[int] = set()
    ok = 0
    failed = 0

    # Pre-load existing scores to enable UPSERT semantics.
    existing = {
        s.stock_id: s
        for s in db.execute(select(StockScore)).scalars().all()
    }

    for stock in stocks:
        if stock.id in seen_ids:
            continue
        seen_ids.add(stock.id)
        try:
            new_score = compute_score(db, stock)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] compute_score failed for {stock.ticker}: {exc}")
            failed += 1
            continue
        prev = existing.get(stock.id)
        if prev is None:
            db.add(new_score)
        else:
            prev.composite = new_score.composite
            prev.quality = new_score.quality
            prev.growth = new_score.growth
            prev.value = new_score.value
            prev.momentum = new_score.momentum
            prev.sentiment = new_score.sentiment
            prev.risk_tier = new_score.risk_tier
            prev.computed_at = new_score.computed_at
            prev.breakdown = new_score.breakdown
        ok += 1

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[score] commit failed: {exc}")
        db.rollback()
        return 0
    if failed:
        logger.info(f"[score] recompute_all: ok={ok} failed={failed}")
    else:
        logger.info(f"[score] recompute_all: ok={ok}")
    return ok
