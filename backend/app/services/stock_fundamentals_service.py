"""Fetch company fundamentals + micro-data + insider transactions + analyst
recommendations from yfinance in a single cached call per ticker.

Why one combined service: each yfinance Ticker creation is cheap, but Yahoo
rate-limits the slow endpoints (Ticker.info, Ticker.recommendations,
Ticker.insider_transactions). Bundling them into one fetch + 24h TTL cache
amortises the cost across every UI subview that needs any of these fields.
"""
import math
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from loguru import logger


@dataclass
class AnnualPoint:
    fiscal_year_end: str
    revenue: float | None
    net_income: float | None
    eps: float | None


@dataclass
class QuarterlyPoint:
    """Reported quarterly revenue + EPS (historical only — yfinance doesn't
    expose forward revenue per-quarter in a clean format)."""
    fiscal_quarter_end: str
    revenue: float | None
    eps: float | None


@dataclass
class EarningsPoint:
    """One quarter of earnings — historical (with reported) or forward (estimate only)."""
    date: str
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None
    revenue_estimate: float | None = None
    revenue_reported: float | None = None


@dataclass
class InsiderTransaction:
    insider: str
    position: str
    transaction: str        # e.g. "Sale at price 275.00"
    date: str
    shares: int | None
    value: float | None     # USD


@dataclass
class AnalystRating:
    period: str             # "0m" / "-1m" / "-2m" / "-3m"
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


@dataclass
class AnalystPriceTarget:
    # Defaults so Fundamentals.price_target = field(default_factory=AnalystPriceTarget)
    # works without needing to pass all 5 fields.
    current: float | None = None
    low: float | None = None
    mean: float | None = None
    median: float | None = None
    high: float | None = None


@dataclass
class MicroData:
    """Snapshot fundamentals from Ticker.info — slow endpoint, cached 24h."""
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    beta: float | None = None
    dividend_yield: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_to_ebitda: float | None = None
    return_on_equity: float | None = None
    debt_to_equity: float | None = None
    profit_margins: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None


@dataclass
class Fundamentals:
    ticker: str
    annual: list[AnnualPoint] = field(default_factory=list)
    quarterly: list[QuarterlyPoint] = field(default_factory=list)
    earnings: list[EarningsPoint] = field(default_factory=list)
    next_earnings_date: str | None = None
    next_eps_estimate: float | None = None
    micro: MicroData = field(default_factory=MicroData)
    insiders: list[InsiderTransaction] = field(default_factory=list)
    analyst_ratings: list[AnalystRating] = field(default_factory=list)
    price_target: AnalystPriceTarget = field(default_factory=AnalystPriceTarget)
    fetched_at: float = 0.0
    error: str | None = None


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


def _safe_int(v: Any) -> int | None:
    f = _safe_float(v)
    return int(f) if f is not None else None


def _row_at(df: Any, row_name: str, col: Any) -> Any:
    """Helper: safely lookup df.at[row, col] without raising on missing rows."""
    if df is None or df.empty or row_name not in df.index:
        return None
    try:
        return df.at[row_name, col]
    except Exception:  # noqa: BLE001
        return None


def _extract_annual(inc_stmt: Any) -> list[AnnualPoint]:
    if inc_stmt is None or inc_stmt.empty:
        return []
    rows: list[AnnualPoint] = []
    for col in inc_stmt.columns:
        rows.append(AnnualPoint(
            fiscal_year_end=str(col.date()) if hasattr(col, "date") else str(col),
            revenue=_safe_float(_row_at(inc_stmt, "Total Revenue", col)),
            net_income=_safe_float(_row_at(inc_stmt, "Net Income", col)),
            eps=_safe_float(_row_at(inc_stmt, "Diluted EPS", col)),
        ))
    rows.reverse()  # chronological
    return rows


def _extract_quarterly(qinc_stmt: Any) -> list[QuarterlyPoint]:
    if qinc_stmt is None or qinc_stmt.empty:
        return []
    rows: list[QuarterlyPoint] = []
    for col in qinc_stmt.columns:
        rows.append(QuarterlyPoint(
            fiscal_quarter_end=str(col.date()) if hasattr(col, "date") else str(col),
            revenue=_safe_float(_row_at(qinc_stmt, "Total Revenue", col)),
            eps=_safe_float(_row_at(qinc_stmt, "Diluted EPS", col)),
        ))
    rows.reverse()
    # Cap at 8 quarters
    return rows[-8:]


def _extract_earnings(ed: Any) -> tuple[list[EarningsPoint], str | None, float | None]:
    if ed is None or ed.empty:
        return [], None, None

    historical: list[EarningsPoint] = []
    next_date: str | None = None
    next_estimate: float | None = None

    ed_sorted = ed.sort_index(ascending=True)
    for ts, row in ed_sorted.iterrows():
        d = str(ts.date()) if hasattr(ts, "date") else str(ts)
        est = _safe_float(row.get("EPS Estimate"))
        rep = _safe_float(row.get("Reported EPS"))
        surp = _safe_float(row.get("Surprise(%)"))
        # Some yfinance versions also expose Revenue Estimate / Revenue Reported
        rev_est = _safe_float(row.get("Revenue Estimate")) if "Revenue Estimate" in row.index else None
        rev_rep = _safe_float(row.get("Revenue Reported")) if "Revenue Reported" in row.index else None
        if rep is not None:
            historical.append(EarningsPoint(
                date=d, eps_estimate=est, eps_reported=rep, surprise_pct=surp,
                revenue_estimate=rev_est, revenue_reported=rev_rep,
            ))
        elif next_date is None:
            next_date = d
            next_estimate = est

    historical = historical[-8:]
    return historical, next_date, next_estimate


def _extract_micro(info: dict | None) -> MicroData:
    if not info:
        return MicroData()
    return MicroData(
        trailing_pe=_safe_float(info.get("trailingPE")),
        forward_pe=_safe_float(info.get("forwardPE")),
        peg_ratio=_safe_float(info.get("pegRatio")),
        beta=_safe_float(info.get("beta")),
        dividend_yield=_safe_float(info.get("dividendYield")),
        price_to_book=_safe_float(info.get("priceToBook")),
        price_to_sales=_safe_float(info.get("priceToSalesTrailing12Months")),
        enterprise_to_ebitda=_safe_float(info.get("enterpriseToEbitda")),
        return_on_equity=_safe_float(info.get("returnOnEquity")),
        debt_to_equity=_safe_float(info.get("debtToEquity")),
        profit_margins=_safe_float(info.get("profitMargins")),
        revenue_growth=_safe_float(info.get("revenueGrowth")),
        earnings_growth=_safe_float(info.get("earningsGrowth")),
    )


def _extract_insiders(it_df: Any, limit: int = 10) -> list[InsiderTransaction]:
    if it_df is None or it_df.empty:
        return []
    out: list[InsiderTransaction] = []
    for _, row in it_df.head(limit).iterrows():
        date_v = row.get("Start Date")
        date_s = str(date_v.date()) if hasattr(date_v, "date") else str(date_v) if date_v is not None else ""
        out.append(InsiderTransaction(
            insider=str(row.get("Insider") or "").strip(),
            position=str(row.get("Position") or "").strip(),
            transaction=str(row.get("Text") or row.get("Transaction") or "").strip(),
            date=date_s,
            shares=_safe_int(row.get("Shares")),
            value=_safe_float(row.get("Value")),
        ))
    return out


def _extract_ratings(rec_df: Any) -> list[AnalystRating]:
    if rec_df is None or rec_df.empty:
        return []
    out: list[AnalystRating] = []
    for _, row in rec_df.iterrows():
        out.append(AnalystRating(
            period=str(row.get("period") or ""),
            strong_buy=_safe_int(row.get("strongBuy")) or 0,
            buy=_safe_int(row.get("buy")) or 0,
            hold=_safe_int(row.get("hold")) or 0,
            sell=_safe_int(row.get("sell")) or 0,
            strong_sell=_safe_int(row.get("strongSell")) or 0,
        ))
    return out


def _extract_price_target(pt: Any) -> AnalystPriceTarget:
    if not pt or not isinstance(pt, dict):
        return AnalystPriceTarget(current=None, low=None, mean=None, median=None, high=None)
    return AnalystPriceTarget(
        current=_safe_float(pt.get("current")),
        low=_safe_float(pt.get("low")),
        mean=_safe_float(pt.get("mean")),
        median=_safe_float(pt.get("median")),
        high=_safe_float(pt.get("high")),
    )


def _fetch_fresh(ticker: str) -> Fundamentals:
    from app.services import yfinance_health
    import yfinance as yf

    f = Fundamentals(ticker=ticker, fetched_at=time.time())

    if yfinance_health.is_open():
        f.error = "yfinance circuit breaker is open (rate-limited); try again later"
        logger.info(f"[fundamentals] breaker OPEN — returning empty payload for {ticker}")
        return f

    saw_success = False
    def _maybe_record(exc: Exception | None) -> None:
        if exc is None:
            return
        if yfinance_health.is_rate_limit_error(exc):
            yfinance_health.record_failure(f"fundamentals {ticker}: {exc}")
    try:
        t = yf.Ticker(ticker)
        # Each of these is independently network-bound and may individually
        # fail; we wrap each in a try so a single 429 doesn't blank out
        # the whole payload.
        try:
            f.annual = _extract_annual(t.income_stmt)
            if f.annual: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] annual {ticker}: {e}")
            _maybe_record(e)
        try:
            f.quarterly = _extract_quarterly(t.quarterly_income_stmt)
            if f.quarterly: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] quarterly {ticker}: {e}")
            _maybe_record(e)
        try:
            hist, nxt_date, nxt_est = _extract_earnings(t.earnings_dates)
            f.earnings = hist
            f.next_earnings_date = nxt_date
            f.next_eps_estimate = nxt_est
            if hist or nxt_date: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] earnings {ticker}: {e}")
            _maybe_record(e)
        try:
            f.micro = _extract_micro(t.get_info())
            if any(getattr(f.micro, k) is not None for k in vars(f.micro)): saw_success = True
        except Exception as e:
            logger.debug(f"[fund] info {ticker}: {e}")
            _maybe_record(e)
        try:
            f.insiders = _extract_insiders(t.insider_transactions)
            if f.insiders: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] insiders {ticker}: {e}")
            _maybe_record(e)
        try:
            f.analyst_ratings = _extract_ratings(t.recommendations)
            if f.analyst_ratings: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] recommendations {ticker}: {e}")
            _maybe_record(e)
        try:
            f.price_target = _extract_price_target(t.analyst_price_targets)
            if f.price_target.mean is not None: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] price_target {ticker}: {e}")
            _maybe_record(e)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fundamentals] top-level failure for {ticker}: {e}")
        f.error = str(e)
        if yfinance_health.is_rate_limit_error(e):
            yfinance_health.record_failure(f"fundamentals top-level {ticker}: {e}")
    # Per-source metrics: count this fetch attempt
    from app.services import data_source_metrics
    if saw_success:
        yfinance_health.record_success()
        data_source_metrics.record_success("yfinance", "fundamentals")
    elif f.error or not saw_success:
        data_source_metrics.record_failure(
            "yfinance", "fundamentals",
            reason=f.error or f"empty payload for {ticker}",
        )
    return f


def get_fundamentals(ticker: str, *, force_refresh: bool = False) -> Fundamentals:
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
    with _CACHE_LOCK:
        _CACHE.clear()
