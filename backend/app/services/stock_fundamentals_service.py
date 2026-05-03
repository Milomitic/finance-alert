"""Fetch company fundamentals (revenue, net income, EPS history + earnings
surprises and next-quarter estimate) from yfinance.

Cached in-memory with a 24h TTL — fundamentals only change quarterly. Network
failures are non-fatal: empty payload is returned and logged.
"""
import math
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from loguru import logger


@dataclass
class AnnualPoint:
    fiscal_year_end: str  # ISO date YYYY-MM-DD
    revenue: float | None
    net_income: float | None
    eps: float | None     # diluted EPS for the year (None if unavailable)


@dataclass
class EarningsPoint:
    """One quarter of earnings — historical (with reported) or forward (estimate only)."""
    date: str             # ISO date of the earnings release
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None  # (reported - estimate) / |estimate| * 100


@dataclass
class Fundamentals:
    ticker: str
    annual: list[AnnualPoint] = field(default_factory=list)
    earnings: list[EarningsPoint] = field(default_factory=list)
    next_earnings_date: str | None = None
    next_eps_estimate: float | None = None
    fetched_at: float = 0.0
    error: str | None = None


# Simple in-process TTL cache. 24h is fine since fundamentals change quarterly.
_CACHE: dict[str, Fundamentals] = {}
_CACHE_LOCK = Lock()
_TTL_SECONDS = 24 * 60 * 60


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _extract_annual(inc_stmt: Any) -> list[AnnualPoint]:
    """income_stmt is a DataFrame with columns = year-end Timestamps and
    rows = field names. We pull Total Revenue, Net Income, Diluted EPS."""
    if inc_stmt is None or inc_stmt.empty:
        return []
    rows: list[AnnualPoint] = []
    for col in inc_stmt.columns:
        rev = inc_stmt.at["Total Revenue", col] if "Total Revenue" in inc_stmt.index else None
        ni = inc_stmt.at["Net Income", col] if "Net Income" in inc_stmt.index else None
        eps = inc_stmt.at["Diluted EPS", col] if "Diluted EPS" in inc_stmt.index else None
        rows.append(
            AnnualPoint(
                fiscal_year_end=str(col.date()) if hasattr(col, "date") else str(col),
                revenue=_safe_float(rev),
                net_income=_safe_float(ni),
                eps=_safe_float(eps),
            )
        )
    # Newest first → reverse to chronological for the UI line chart
    rows.reverse()
    return rows


def _extract_earnings(ed: Any) -> tuple[list[EarningsPoint], str | None, float | None]:
    """earnings_dates DataFrame: index=Earnings Date, columns include
    'EPS Estimate', 'Reported EPS', 'Surprise(%)'. Returns
    (historical_quarters, next_date, next_estimate)."""
    if ed is None or ed.empty:
        return [], None, None

    historical: list[EarningsPoint] = []
    next_date: str | None = None
    next_estimate: float | None = None

    # Index is timezone-aware Timestamp. Sort ascending so we can split
    # historical (with Reported EPS) from forthcoming (Reported EPS NaN).
    ed_sorted = ed.sort_index(ascending=True)
    for ts, row in ed_sorted.iterrows():
        d = str(ts.date()) if hasattr(ts, "date") else str(ts)
        est = _safe_float(row.get("EPS Estimate"))
        rep = _safe_float(row.get("Reported EPS"))
        surp = _safe_float(row.get("Surprise(%)"))
        if rep is not None:
            historical.append(EarningsPoint(
                date=d, eps_estimate=est, eps_reported=rep, surprise_pct=surp,
            ))
        elif next_date is None:  # first not-yet-reported quarter
            next_date = d
            next_estimate = est

    # Keep only the last 8 historical quarters
    historical = historical[-8:]
    return historical, next_date, next_estimate


def _fetch_fresh(ticker: str) -> Fundamentals:
    import yfinance as yf
    f = Fundamentals(ticker=ticker, fetched_at=time.time())
    try:
        t = yf.Ticker(ticker)
        f.annual = _extract_annual(t.income_stmt)
        hist, nxt_date, nxt_est = _extract_earnings(t.earnings_dates)
        f.earnings = hist
        f.next_earnings_date = nxt_date
        f.next_eps_estimate = nxt_est
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fundamentals] fetch failed for {ticker}: {e}")
        f.error = str(e)
    return f


def get_fundamentals(ticker: str, *, force_refresh: bool = False) -> Fundamentals:
    """Return fundamentals (cached 24h). Network call only on cache miss/stale
    or when `force_refresh=True`."""
    now = time.time()
    if not force_refresh:
        with _CACHE_LOCK:
            cached = _CACHE.get(ticker)
            if cached is not None and (now - cached.fetched_at) < _TTL_SECONDS:
                return cached
    fresh = _fetch_fresh(ticker)
    with _CACHE_LOCK:
        _CACHE[ticker] = fresh
    return fresh


def clear_cache() -> None:
    """For tests."""
    with _CACHE_LOCK:
        _CACHE.clear()
