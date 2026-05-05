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
class AnalystAction:
    """One historical analyst rating action (upgrade/downgrade/initiation).

    Recent yfinance versions also expose per-analyst price targets via
    upgrades_downgrades; we surface them when present so the UI can show
    the actual dollar number alongside the grade change. Older yfinance
    versions don't include these columns — the optional fields stay None
    and the UI gracefully shows "—".
    """
    date: str          # ISO date YYYY-MM-DD
    firm: str
    to_grade: str
    from_grade: str
    action: str        # e.g. "main", "up", "down", "init", "reit"
    # Per-analyst price target the firm assigned in this action. Optional —
    # only populated when yfinance returns the `currentPriceTarget` column.
    current_price_target: float | None = None
    # The same firm's previous target before this action; "Raises 287→296"
    # is more informative than "Raises to 296" alone.
    prior_price_target: float | None = None
    # Yahoo's labeled change — "Raises", "Lowers", "Maintains", or "Initiates".
    # Distinct from `action` (which is the rating-grade movement code) and
    # captured separately because a Maintain on the rating can still pair
    # with a target raise/lower.
    price_target_action: str | None = None


@dataclass
class MicroData:
    """Snapshot fundamentals from Ticker.info — slow endpoint, cached 24h."""
    # Valuation multiples
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    beta: float | None = None
    dividend_yield: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_to_ebitda: float | None = None
    enterprise_value: float | None = None
    book_value: float | None = None       # per share
    # Profitability / quality
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    profit_margins: float | None = None
    operating_margins: float | None = None
    gross_margins: float | None = None
    # Leverage / liquidity
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    # Growth
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    # Cash flow
    free_cashflow: float | None = None
    operating_cashflow: float | None = None
    # Income / payout
    payout_ratio: float | None = None
    # Holdings & sentiment
    held_percent_insiders: float | None = None
    held_percent_institutions: float | None = None
    # Performance vs market
    fifty_two_week_change: float | None = None
    sp500_fifty_two_week_change: float | None = None


@dataclass
class CompanyProfile:
    """Identity / "anagrafica" data extracted from yfinance Ticker.info.

    Separated from MicroData (which is purely numeric ratios) because these
    are textual/descriptive fields with very different cache/render semantics
    — the long_business_summary in particular is the only multi-paragraph
    text in the payload. Optional everywhere; the UI gracefully hides
    unavailable fields rather than showing "—".
    """
    long_business_summary: str | None = None
    website: str | None = None
    employees: int | None = None
    city: str | None = None
    country: str | None = None
    # First named officer from yfinance's companyOfficers list, when present.
    # Used as a "CEO / lead exec" hint — we don't try to parse the title
    # string because yfinance is inconsistent (CEO / Chief Executive Officer / etc.).
    ceo: str | None = None
    # IPO / first-trade year, when yfinance exposes it. Most info dicts don't.
    founded: int | None = None


@dataclass
class Fundamentals:
    ticker: str
    annual: list[AnnualPoint] = field(default_factory=list)
    quarterly: list[QuarterlyPoint] = field(default_factory=list)
    earnings: list[EarningsPoint] = field(default_factory=list)
    next_earnings_date: str | None = None
    next_eps_estimate: float | None = None
    next_revenue_estimate: float | None = None
    micro: MicroData = field(default_factory=MicroData)
    profile: CompanyProfile = field(default_factory=CompanyProfile)
    insiders: list[InsiderTransaction] = field(default_factory=list)
    analyst_ratings: list[AnalystRating] = field(default_factory=list)
    analyst_actions: list[AnalystAction] = field(default_factory=list)
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
    # Cap at 20 quarters (~5y) to mirror the earnings_dates cap and give
    # the FundamentalsCard longer-trend visibility.
    return rows[-20:]


def _extract_earnings(
    ed: Any,
) -> tuple[list[EarningsPoint], str | None, float | None, float | None]:
    """Parse yfinance's earnings_dates DataFrame into history + next-up.

    Returns (historical, next_date, next_eps_estimate, next_revenue_estimate).
    The next-up triplet describes the FIRST upcoming earnings event that
    yfinance has on calendar (rep == None means it hasn't happened yet);
    we capture date + EPS est + revenue est so the UI can render a
    forward-looking row in the quarterly view.
    """
    if ed is None or ed.empty:
        return [], None, None, None

    historical: list[EarningsPoint] = []
    next_date: str | None = None
    next_estimate: float | None = None
    next_rev_estimate: float | None = None

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
            next_rev_estimate = rev_est

    # 20 quarters ≈ 5 years of earnings history. Bumped from 8 (=2y) so the
    # FundamentalsCard can show longer trends without re-fetching. yfinance
    # typically returns 12-16 rows so this cap usually doesn't bite, but
    # keeps the L2 payload bounded against pathological responses.
    historical = historical[-20:]
    return historical, next_date, next_estimate, next_rev_estimate


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
        enterprise_value=_safe_float(info.get("enterpriseValue")),
        book_value=_safe_float(info.get("bookValue")),
        return_on_equity=_safe_float(info.get("returnOnEquity")),
        return_on_assets=_safe_float(info.get("returnOnAssets")),
        profit_margins=_safe_float(info.get("profitMargins")),
        operating_margins=_safe_float(info.get("operatingMargins")),
        gross_margins=_safe_float(info.get("grossMargins")),
        debt_to_equity=_safe_float(info.get("debtToEquity")),
        current_ratio=_safe_float(info.get("currentRatio")),
        quick_ratio=_safe_float(info.get("quickRatio")),
        revenue_growth=_safe_float(info.get("revenueGrowth")),
        earnings_growth=_safe_float(info.get("earningsGrowth")),
        free_cashflow=_safe_float(info.get("freeCashflow")),
        operating_cashflow=_safe_float(info.get("operatingCashflow")),
        payout_ratio=_safe_float(info.get("payoutRatio")),
        held_percent_insiders=_safe_float(info.get("heldPercentInsiders")),
        held_percent_institutions=_safe_float(info.get("heldPercentInstitutions")),
        fifty_two_week_change=_safe_float(info.get("52WeekChange")),
        sp500_fifty_two_week_change=_safe_float(info.get("SandP52WeekChange")),
    )


def _extract_profile(info: dict | None) -> CompanyProfile:
    """Pull identity fields from `Ticker.info`. yfinance is inconsistent —
    fields can be present, missing, or empty-string. We coerce empty-string
    and whitespace-only to None so the frontend doesn't render empty UI
    chrome around no content.
    """
    if not info:
        return CompanyProfile()

    def _str(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    # CEO: pick the first officer with a non-empty name. yfinance's
    # `companyOfficers` is a list of dicts in officer-rank order.
    ceo: str | None = None
    officers = info.get("companyOfficers") or []
    if isinstance(officers, list):
        for o in officers:
            if isinstance(o, dict):
                name = _str(o.get("name"))
                if name:
                    ceo = name
                    break

    # Founded year: yfinance occasionally exposes `firstTradeDateEpochUtc`
    # (seconds since epoch) — useful as a proxy for "when did this start
    # trading". Most tickers don't have it, in which case we leave None.
    founded: int | None = None
    epoch = info.get("firstTradeDateEpochUtc")
    if isinstance(epoch, int | float) and epoch > 0:
        try:
            from datetime import UTC, datetime
            founded = datetime.fromtimestamp(float(epoch), tz=UTC).year
        except (OSError, OverflowError, ValueError):
            founded = None

    return CompanyProfile(
        long_business_summary=_str(info.get("longBusinessSummary")),
        website=_str(info.get("website")),
        employees=_safe_int(info.get("fullTimeEmployees")),
        city=_str(info.get("city")),
        country=_str(info.get("country")),
        ceo=ceo,
        founded=founded,
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


def _extract_actions(df: Any, limit: int = 12) -> list[AnalystAction]:
    """yfinance Ticker.upgrades_downgrades returns a DataFrame indexed by
    GradeDate. Recent yfinance versions add 3 columns beyond the original
    Firm/ToGrade/FromGrade/Action: priceTargetAction, currentPriceTarget,
    priorPriceTarget. We capture them when present, leave None otherwise so
    the API response is forward-compatible with older yfinance.
    Most-recent `limit` entries, newest first."""
    if df is None or df.empty:
        return []
    cols = set(df.columns)
    has_price_target_cols = "currentPriceTarget" in cols

    out: list[AnalystAction] = []
    # Sort descending by index (date) so newest first
    df_sorted = df.sort_index(ascending=False)
    for ts, row in df_sorted.head(limit).iterrows():
        d = str(ts.date()) if hasattr(ts, "date") else str(ts)
        # Per-analyst targets only attempted when the column set indicates
        # this yfinance version exposes them — avoids false-positive None
        # warnings on older versions.
        cur_pt = _safe_float(row.get("currentPriceTarget")) if has_price_target_cols else None
        prior_pt = _safe_float(row.get("priorPriceTarget")) if has_price_target_cols else None
        pt_action_raw = row.get("priceTargetAction") if has_price_target_cols else None
        pt_action = (
            str(pt_action_raw).strip() if pt_action_raw is not None and str(pt_action_raw).strip() else None
        )
        out.append(AnalystAction(
            date=d,
            firm=str(row.get("Firm") or "").strip(),
            to_grade=str(row.get("ToGrade") or "").strip(),
            from_grade=str(row.get("FromGrade") or "").strip(),
            action=str(row.get("Action") or "").strip(),
            current_price_target=cur_pt,
            prior_price_target=prior_pt,
            price_target_action=pt_action,
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
            hist, nxt_date, nxt_est, nxt_rev_est = _extract_earnings(t.earnings_dates)
            f.earnings = hist
            f.next_earnings_date = nxt_date
            f.next_eps_estimate = nxt_est
            f.next_revenue_estimate = nxt_rev_est
            if hist or nxt_date: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] earnings {ticker}: {e}")
            _maybe_record(e)
        try:
            # Single info() call — both micro fundamentals and the company
            # profile come from the same dict, so pulling them together
            # avoids a duplicate slow-endpoint roundtrip.
            info = t.get_info()
            f.micro = _extract_micro(info)
            f.profile = _extract_profile(info)
            if any(getattr(f.micro, k) is not None for k in vars(f.micro)): saw_success = True
            if f.profile.long_business_summary or f.profile.website:
                saw_success = True
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
        try:
            f.analyst_actions = _extract_actions(t.upgrades_downgrades)
            if f.analyst_actions: saw_success = True
        except Exception as e:
            logger.debug(f"[fund] upgrades_downgrades {ticker}: {e}")
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
    """Two-tier cache:
      L1 = in-memory _CACHE (microseconds)
      L2 = fetch_cache table (DB; survives restarts)
    Network only fired when both miss / stale or `force_refresh=True`.

    L2 access opens its own short-lived SessionLocal — `get_fundamentals`
    is called from request handlers, background tasks, and scripts which
    each manage their own sessions; coupling this function to a passed-in
    Session would require updating every call site. The L2 read+write is
    a single cheap query each, so the per-call session is fine.
    """
    now = time.time()
    if not force_refresh:
        # L1
        with _CACHE_LOCK:
            cached = _CACHE.get(ticker)
            if cached is not None and (now - cached.fetched_at) < _TTL_SECONDS:
                return cached
        # L2 — try DB. Imported lazily to avoid an import cycle (the
        # store module imports the dataclasses defined above).
        try:
            from app.core.db import SessionLocal
            from app.services import fetch_cache_store
            with SessionLocal() as db:
                from_db = fetch_cache_store.read_fundamentals(
                    db, ticker, _TTL_SECONDS
                )
            if from_db is not None:
                # Hydrate L1 so subsequent requests in this process skip
                # the DB round-trip.
                with _CACHE_LOCK:
                    _CACHE[ticker] = from_db
                return from_db
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[fund] L2 read failed for {ticker}: {exc}")

    # Both layers missed / stale → upstream fetch
    fresh = _fetch_fresh(ticker)
    with _CACHE_LOCK:
        _CACHE[ticker] = fresh
    # UPSERT to L2. Non-fatal if the DB write blows up — L1 still serves
    # the in-process consumers and we'll retry on the next refresh cycle.
    # Don't persist error rows: a transient yfinance failure shouldn't
    # poison the cache for 24h.
    if not fresh.error:
        try:
            from app.core.db import SessionLocal
            from app.services import fetch_cache_store
            with SessionLocal() as db:
                fetch_cache_store.write_fundamentals(db, fresh)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[fund] L2 write failed for {ticker}: {exc}")
    return fresh


def clear_cache() -> None:
    """Clear BOTH layers (L1 in-memory + L2 DB rows). Used by tests to
    isolate themselves; safe in production too — `clear_cache` is only
    called by intentional refresh paths."""
    with _CACHE_LOCK:
        _CACHE.clear()
    try:
        from app.core.db import SessionLocal
        from app.models import FetchCache
        with SessionLocal() as db:
            db.query(FetchCache).filter_by(kind="fundamentals").delete()
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[fund] L2 clear failed: {exc}")


def hydrate_l1_from_db() -> int:
    """Populate the in-memory L1 cache from the persistent L2 table. Call
    once at app startup so the first request after a restart hits L1
    instantly instead of round-tripping the DB per ticker.

    Returns the number of fresh entries hydrated."""
    try:
        from app.core.db import SessionLocal
        from app.services import fetch_cache_store
        with SessionLocal() as db:
            entries = fetch_cache_store.hydrate_all_fundamentals(db, _TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[fund] L1 hydration failed: {exc}")
        return 0
    with _CACHE_LOCK:
        _CACHE.update(entries)
    if entries:
        logger.info(f"[fund] hydrated L1 with {len(entries)} entries from L2")
    return len(entries)
