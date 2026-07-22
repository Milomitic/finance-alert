"""Fetch company fundamentals + micro-data + insider transactions + analyst
recommendations from yfinance in a single cached call per ticker.

Why one combined service: each yfinance Ticker creation is cheap, but Yahoo
rate-limits the slow endpoints (Ticker.info, Ticker.recommendations,
Ticker.insider_transactions). Bundling them into one fetch + 24h TTL cache
amortises the cost across every UI subview that needs any of these fields.
"""
import math
import random
import time
from dataclasses import dataclass, field
from datetime import date
from threading import Lock
from typing import Any

import pandas as pd
from loguru import logger

from app.services.currency_units import is_minor_unit


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
    time_utc: str | None = None  # HH:MM UTC, used for pre/after-market classification


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

    Source attribution: actions can come from EITHER yfinance's structured
    `upgrades_downgrades` table OR from regex extraction of news headlines
    (`news_analyst_extractor`). The `from_news` flag distinguishes them so
    the UI can render a "from news" badge with click-through to the article.
    Dedup at merge time (same firm, same calendar week) ensures we don't
    double-count when both sources surface the same action.
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
    # True when this row was extracted from a news headline rather than
    # yfinance's structured upgrades_downgrades. Drives the "news" badge
    # in the UI. False (default) preserves backwards compatibility.
    from_news: bool = False
    # When `from_news`, the article URL the user clicks through to.
    source_link: str | None = None
    # When `from_news`, the original headline text (the UI may show it
    # as a hover-title on the firm cell).
    source_title: str | None = None


@dataclass
class MicroData:
    """Snapshot fundamentals from Ticker.info — slow endpoint, cached 24h.

    Comprehensive coverage of every numeric field yfinance reliably exposes
    on `Ticker.info` for valuation / quality / earnings / cash / share /
    dividend / analyst / risk analysis. Each field is optional because:
      - yfinance returns different subsets per ticker (foreign listings
        skip US-specific governance scores; IPOs lack TTM rows; etc.).
      - The frontend renders "—" gracefully when a field is None.
    Bumping schema version in `fetch_cache_store` invalidates old payloads
    so users naturally get the richer dataset on next visit.
    """
    # ── Valuation multiples ────────────────────────────────────────────
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    trailing_peg_ratio: float | None = None  # newer "trailingPegRatio"
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_to_ebitda: float | None = None
    enterprise_to_revenue: float | None = None  # EV/Sales — capital-structure-agnostic
    enterprise_value: float | None = None
    book_value: float | None = None             # per share
    price_eps_current_year: float | None = None # forward P/E using current-year EPS
    # ── Profitability / margins ────────────────────────────────────────
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    profit_margins: float | None = None
    operating_margins: float | None = None
    gross_margins: float | None = None
    ebitda_margins: float | None = None
    ebitda: float | None = None
    gross_profits: float | None = None
    net_income_to_common: float | None = None    # net income to common shareholders
    # ── Earnings / EPS ─────────────────────────────────────────────────
    eps_trailing: float | None = None
    eps_forward: float | None = None
    eps_current_year: float | None = None        # current-year analyst estimate
    earnings_quarterly_growth: float | None = None  # QoQ EPS growth (fraction)
    # ── Revenue ────────────────────────────────────────────────────────
    total_revenue: float | None = None
    revenue_per_share: float | None = None
    # ── Leverage / liquidity ───────────────────────────────────────────
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    total_cash: float | None = None
    total_cash_per_share: float | None = None
    total_debt: float | None = None
    # ── Cash flow ──────────────────────────────────────────────────────
    free_cashflow: float | None = None
    operating_cashflow: float | None = None
    # ── Growth ─────────────────────────────────────────────────────────
    # NOTE: as of the current-FY-projection change, `revenue_growth` and
    # `earnings_growth` mean "current-fiscal-year PROJECTED growth"
    # (analyst-estimate-inclusive: reported quarters + consensus for the
    # quarters not yet reported, vs prior-FY actual) WHEN that projection is
    # available — falling back to the trailing-YoY figure only when it isn't.
    # The raw projection (yfinance earnings_estimate/revenue_estimate `0y`
    # row's `growth`) is preserved in *_growth_curr_fy below for transparency.
    revenue_growth: float | None = None              # Rev growth: curr-FY projected, trailing-YoY fallback
    earnings_growth: float | None = None             # EPS growth: curr-FY projected, trailing-YoY fallback
    revenue_quarterly_growth: float | None = None    # Rev QoQ (fraction)
    # Raw current-FY consensus growth from yfinance's estimate tables
    # (`0y` row `growth`, a fraction). None when the tables are absent /
    # empty / NaN — in which case the *_growth fields keep the trailing YoY.
    # Kept separate for debugging + so the semantics shift above is auditable.
    eps_growth_curr_fy: float | None = None
    revenue_growth_curr_fy: float | None = None
    # Annualized CAGR over ~5y (computed by us — yfinance doesn't expose
    # multi-year growth). None when <2.5y of history or non-positive
    # endpoints (CAGR is undefined across a sign flip).
    earnings_growth_5y: float | None = None
    revenue_growth_5y: float | None = None
    # ── Dividend ───────────────────────────────────────────────────────
    dividend_rate: float | None = None              # USD/share annual
    dividend_yield: float | None = None             # %, yfinance returns 1.81 = 1.81%
    five_year_avg_dividend_yield: float | None = None
    trailing_annual_dividend_rate: float | None = None
    trailing_annual_dividend_yield: float | None = None  # fraction
    payout_ratio: float | None = None
    # ── Beta / risk ────────────────────────────────────────────────────
    beta: float | None = None
    # ── Shares / float / short interest ────────────────────────────────
    shares_outstanding: float | None = None
    float_shares: float | None = None
    shares_short: float | None = None
    short_ratio: float | None = None
    short_percent_of_float: float | None = None    # fraction, e.g. 0.0147
    # ── Holdings ───────────────────────────────────────────────────────
    held_percent_insiders: float | None = None
    held_percent_institutions: float | None = None
    # ── Analyst aggregate ──────────────────────────────────────────────
    recommendation_mean: float | None = None       # 1.0 (strong buy) - 5.0 (sell)
    number_of_analyst_opinions: float | None = None
    # ── Performance vs market ──────────────────────────────────────────
    fifty_two_week_change: float | None = None
    sp500_fifty_two_week_change: float | None = None
    # ── Governance / risk scores (Yahoo's 1-10 scales; lower = better) ─
    audit_risk: float | None = None
    board_risk: float | None = None
    compensation_risk: float | None = None
    share_holder_rights_risk: float | None = None
    overall_risk: float | None = None


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
    next_earnings_time_utc: str | None = None  # UTC HH:MM
    next_eps_estimate: float | None = None
    next_revenue_estimate: float | None = None
    # Current-FISCAL-YEAR analyst consensus (yfinance earnings_estimate /
    # revenue_estimate `0y` row, `avg` column): full-year EPS + revenue
    # estimates for the FY in progress. Feeds the estimate row at the top of
    # the Fundamentals annual table. None when the tables are absent (thin
    # coverage / non-US) — old L2 rows lack the keys and default here too.
    curr_fy_eps_estimate: float | None = None
    curr_fy_revenue_estimate: float | None = None
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
# TTL bumped from 24h → 7d (2026-05-14). Fundamentals data (P/E, ROE,
# margins, sector, quarterly earnings) doesn't change daily — quarterly
# reports publish every ~90d, sector classifications essentially never.
# The previous 24h TTL was forcing a re-fetch of ~600/1085 tickers on
# every scan (the ones touched on rotating cron windows), costing
# 25-50min per scan in pure yfinance latency on EU stocks where each
# ticker pays ~3s for sub-endpoint 404s (insider/analyst data Yahoo
# doesn't publish for non-US). At 7d we re-fetch ~150/week instead.
# Live price data is on a separate 10s-TTL cache (`live_quote_service`),
# so this change does NOT affect quote freshness.
_TTL_SECONDS = 7 * 24 * 60 * 60
# Negative-cache TTL (6 hours): how long a "permanent error" payload (404
# / no-data / delisted ticker) stays valid in L1+L2 before we re-attempt
# yfinance. Without this, every backend restart re-pays the ~3-5s yfinance
# 404 cost for every dud ticker (~150-200 EU minor stocks in our catalog),
# adding 8-15min to the sector_stats prepass on the first scan post-restart.
# Why 6h and not 24h: a freshly-listed ticker shouldn't stay "404" all day.
# Why not 1h: still leaves enough wasted retries on hourly cron scans.
# Transient errors (rate-limit, circuit-breaker open) are NOT cached at all
# (see `_is_permanent_error`) so yfinance recovery works naturally.
_NEGATIVE_TTL_SECONDS = 6 * 60 * 60


def _is_permanent_error(err: str | None) -> bool:
    """True when an error string represents a stable, ticker-specific failure
    (404, no-data, partial fetch with empty info) — safe to cache. False
    for transient infra errors (rate-limit, circuit breaker, network)
    where caching would just delay recovery.

    The classification is conservative — when in doubt we treat as
    transient (return False) so we don't lock out a ticker that might
    actually have data behind a temporary failure.
    """
    if not err:
        return False
    e = err.lower()
    # Transient — never persist
    if "circuit breaker" in e:
        return False
    if "rate" in e and "limit" in e:
        return False
    if "429" in e or "too many" in e:
        return False
    if "timeout" in e or "timed out" in e:
        return False
    # Permanent — safe to persist for the negative-cache window
    if "no data" in e or "not found" in e or "404" in e:
        return True
    if "partial fetch" in e:  # set when info endpoint returns nothing
        return True
    if "no fundamentals" in e:
        return True
    # Default conservative: treat as transient
    return False


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
) -> tuple[list[EarningsPoint], str | None, float | None, float | None, str | None]:
    """Parse yfinance's earnings_dates DataFrame into history + next-up.

    Returns (historical, next_date, next_eps_estimate, next_revenue_estimate,
    next_time_utc). The next-up tuple describes the FIRST upcoming earnings
    event that yfinance has on calendar (rep == None means it hasn't happened
    yet); we capture date + EPS est + revenue est + UTC release time so the
    UI can render a forward-looking row + sun/moon pre/after-market icon.
    """
    if ed is None or ed.empty:
        return [], None, None, None, None

    historical: list[EarningsPoint] = []
    next_date: str | None = None
    next_estimate: float | None = None
    next_rev_estimate: float | None = None
    next_time_utc: str | None = None

    ed_sorted = ed.sort_index(ascending=True)
    for ts, row in ed_sorted.iterrows():
        d = str(ts.date()) if hasattr(ts, "date") else str(ts)
        # yfinance earnings_dates returns tz-aware Timestamps. Convert
        # to UTC and pluck HH:MM so the calendar can later infer
        # pre/after-market based on the US session boundaries.
        time_utc: str | None = None
        try:
            if hasattr(ts, "tz_convert") and ts.tzinfo is not None:
                ts_utc = ts.tz_convert("UTC")
                time_utc = f"{ts_utc.hour:02d}:{ts_utc.minute:02d}"
        except Exception:
            time_utc = None
        est = _safe_float(row.get("EPS Estimate"))
        rep = _safe_float(row.get("Reported EPS"))
        surp = _safe_float(row.get("Surprise(%)"))
        rev_est = _safe_float(row.get("Revenue Estimate")) if "Revenue Estimate" in row.index else None
        rev_rep = _safe_float(row.get("Revenue Reported")) if "Revenue Reported" in row.index else None
        if rep is not None:
            historical.append(EarningsPoint(
                date=d, eps_estimate=est, eps_reported=rep, surprise_pct=surp,
                revenue_estimate=rev_est, revenue_reported=rev_rep,
                time_utc=time_utc,
            ))
        elif next_date is None and d >= str(date.today()):
            # "Next up" must be TODAY OR LATER. yfinance's earnings_dates
            # keeps orphan rows — scheduled events whose Reported EPS was
            # never reconciled (common on small caps) — so without the date
            # guard a 2-years-old NaN-reported row won as "prossima" and the
            # header showed 15/05/24 as the upcoming earnings in 2026.
            next_date = d
            next_estimate = est
            next_rev_estimate = rev_est
            next_time_utc = time_utc

    # 20 quarters ≈ 5 years of earnings history. Bumped from 8 (=2y) so the
    # FundamentalsCard can show longer trends without re-fetching. yfinance
    # typically returns 12-16 rows so this cap usually doesn't bite, but
    # keeps the L2 payload bounded against pathological responses.
    historical = historical[-20:]
    return historical, next_date, next_estimate, next_rev_estimate, next_time_utc


def _merge_finnhub_actuals_into_earnings(ticker: str, f: "Fundamentals") -> None:
    """Patch the most-recent earnings actuals when yfinance is lagging.

    Called inline during `_fetch_fresh` after yfinance's earnings_dates
    has been parsed. Narrow trigger: ONLY when yfinance left a forward
    event whose date is in the past (`next_earnings_date <= today` =
    release happened, yfinance knows about it but hasn't ingested the
    actual yet). Spends one Finnhub API call per fresh fetch — but
    only for tickers in that narrow lagging-actual window, so the
    free-tier rate budget (60 req/min) is never close to saturated
    even during a full catalog refresh.

    Tickers yfinance doesn't track at all (next_earnings_date null,
    last historical months old — the NVMI case) are NOT caught here.
    Those are handled by the scheduled `refresh_imminent_earnings` job
    which queries the Finnhub calendar globally (one HTTP call for
    the whole catalog) and then calls `patch_earning_from_finnhub` to
    inject the actuals directly, without a per-ticker Finnhub roundtrip.

    Sources are tried in order: Finnhub (fallback #1), then Twelve Data
    (tier-3, a separate free provider) when Finnhub has nothing — so a
    Finnhub rate-limit/outage doesn't leave the actual blank. No-ops
    when BOTH keys are unset or neither has a fresh actual. Exceptions
    caller-swallowed so an upstream outage never blocks the yfinance
    payload.
    """
    from app.services import finnhub_earnings_service, twelvedata_earnings_service
    if not (finnhub_earnings_service.is_enabled()
            or twelvedata_earnings_service.is_enabled()):
        return
    from datetime import date as _date

    nxt = f.next_earnings_date
    if not nxt:
        return  # yfinance has no pending event → no actual-lag to patch
    try:
        nxt_date_obj = _date.fromisoformat(nxt)
    except (TypeError, ValueError):
        return
    if nxt_date_obj > _date.today():
        return  # Future event — no actual to fill in yet

    # yfinance has a past-dated placeholder → ask Finnhub for the actual.
    found = finnhub_earnings_service.fetch_recent_actuals([ticker], days_back=14)
    rec = found.get(ticker)
    if rec is None:
        # Tier-3 fallback: Finnhub had nothing OR its breaker is open
        # (rate-limited). Twelve Data is a SEPARATE free provider, so a
        # Finnhub outage no longer leaves the just-released actual blank.
        # Same record shape (revenue None) — consumed identically below.
        td_found = twelvedata_earnings_service.fetch_recent_actuals(
            [ticker], days_back=14
        )
        rec = td_found.get(ticker)
    if rec is None:
        return  # neither Finnhub nor Twelve Data has a released record
    # Dedup by date: if yfinance ALSO has this date in its history,
    # don't append a duplicate. yfinance's record wins (its surprise%
    # is computed against the consensus estimate yfinance tracks).
    existing_dates = {ep.date for ep in (f.earnings or [])}
    rec_date_str = rec.date.isoformat()
    if rec_date_str in existing_dates:
        # Still clear the "upcoming" slot if it was pointing at this
        # date — the event has been confirmed as historical.
        if nxt == rec_date_str:
            f.next_earnings_date = None
            f.next_earnings_time_utc = None
            f.next_eps_estimate = None
            f.next_revenue_estimate = None
        return
    # Compute surprise % from the Finnhub actuals. yfinance uses
    # `Surprise(%) = (Reported - Estimate) / |Estimate| * 100`; mirror
    # that formula so the row stays comparable across sources.
    surprise_pct: float | None = None
    if (
        rec.eps_actual is not None
        and rec.eps_estimate is not None
        and rec.eps_estimate != 0
    ):
        surprise_pct = (rec.eps_actual - rec.eps_estimate) / abs(rec.eps_estimate) * 100.0
    point = EarningsPoint(
        date=rec_date_str,
        eps_estimate=rec.eps_estimate,
        eps_reported=rec.eps_actual,
        surprise_pct=surprise_pct,
        revenue_estimate=rec.revenue_estimate,
        revenue_reported=rec.revenue_actual,
        time_utc=None,  # Finnhub gives `hour` as 'amc'/'bmo' — no clock time
    )
    f.earnings = (f.earnings or []) + [point]
    # Demote the "upcoming" slot — the event just became historical.
    # Guard prevents wiping a yfinance "next" pointing at a future event
    # in the rare case Finnhub patched in a different, earlier date.
    f.next_earnings_date = None
    f.next_earnings_time_utc = None
    f.next_eps_estimate = None
    f.next_revenue_estimate = None
    logger.info(
        f"[fund] {ticker}: patched earnings actual from "
        f"{type(rec).__name__} (date={rec.date} eps_actual={rec.eps_actual})"
    )


def _merge_finnhub_revenue(ticker: str, f: "Fundamentals") -> None:
    """Backfill revenue estimate/actual on the earnings history + the
    next event from Finnhub.

    Why this exists: yfinance's `Ticker.earnings_dates` carries ONLY
    EPS columns (EPS Estimate / Reported EPS / Surprise%) — it has no
    revenue at all — so without this every "Revenue stim." / "Revenue
    ultimo" cell in the UI is blank. Finnhub's earnings calendar DOES
    expose `revenueEstimate` / `revenueActual`.

    Cost: ONE per-symbol Finnhub call, behind the 7-day fundamentals
    TTL (only stale tickers refetch). During a full catalog backfill
    the 60/min free-tier may 429 on some tickers — `fetch_calendar`
    returns [] on 429, so those just stay revenue-less until the next
    refresh cycle fills them in. Graceful, progressive, never raises.

    Date matching is tolerant (±2 days): yfinance and Finnhub
    occasionally disagree by a day on the same earnings event
    (timezone / BMO-AMC classification).
    """
    from app.services import finnhub_earnings_service
    if not finnhub_earnings_service.is_enabled():
        return

    from datetime import date as _date
    from datetime import timedelta as _td

    needs_history = any(
        ep.revenue_estimate is None or ep.revenue_reported is None
        for ep in (f.earnings or [])
    )
    needs_next = (
        f.next_earnings_date is not None and f.next_revenue_estimate is None
    )
    if not (needs_history or needs_next):
        return  # nothing to fill

    today = _date.today()
    oldest = today - _td(days=920)  # ~2.5y default window
    parsed_dates: list[_date] = []
    for ep in (f.earnings or []):
        try:
            parsed_dates.append(_date.fromisoformat(ep.date[:10]))
        except (TypeError, ValueError):
            continue
    if parsed_dates:
        oldest = min(parsed_dates) - _td(days=2)
    to_date = today + _td(days=120)

    recs = finnhub_earnings_service.fetch_calendar(
        from_date=oldest, to_date=to_date, symbol=ticker,
    )
    if not recs:
        return

    def _closest(date_str: str | None):
        if not date_str:
            return None
        try:
            d = _date.fromisoformat(date_str[:10])
        except (TypeError, ValueError):
            return None
        best = None
        best_gap = 3  # accept at most ±2 days
        for r in recs:
            gap = abs((r.date - d).days)
            if gap < best_gap:
                best, best_gap = r, gap
        return best

    filled = 0
    for ep in (f.earnings or []):
        rec = _closest(ep.date)
        if rec is None:
            continue
        if ep.revenue_estimate is None and rec.revenue_estimate is not None:
            ep.revenue_estimate = rec.revenue_estimate
            filled += 1
        if ep.revenue_reported is None and rec.revenue_actual is not None:
            ep.revenue_reported = rec.revenue_actual
            filled += 1

    if needs_next:
        rec = _closest(f.next_earnings_date)
        if rec is not None and rec.revenue_estimate is not None:
            f.next_revenue_estimate = rec.revenue_estimate
            filled += 1

    if filled:
        logger.info(
            f"[fund] {ticker}: backfilled {filled} revenue field(s) "
            f"from Finnhub ({len(recs)} cal rows)"
        )


def patch_earning_from_finnhub(ticker: str, rec) -> bool:
    """Inject a pre-fetched Finnhub earnings record into the cached
    Fundamentals (L1+L2) for a single ticker without a fresh yfinance
    fetch and without a per-ticker Finnhub HTTP call.

    Designed for the `refresh_imminent_earnings` job: the job has
    already fetched the GLOBAL Finnhub calendar (one HTTP request for
    the whole catalog) and holds {ticker: FinnhubEarning} in memory.
    Calling this for each catalog match is cheap (DB write only) and
    keeps the merge logic centralized.

    Behavior:
      - If the ticker isn't in L1+L2 (never fetched), no-op — there's
        no Fundamentals object to patch. Next user view will fetch
        fresh via the normal path.
      - If the record's date is already in `f.earnings`, no-op (no
        duplicates).
      - Otherwise, append a new EarningsPoint, demote the "upcoming"
        slot, and rewrite both cache layers.

    Returns True iff the cache was modified — useful for the job to
    log "N stocks patched, M no-ops". `rec` is typed loosely as `Any`
    so the import of `FinnhubEarning` stays optional for callers that
    test this in isolation; runtime checks are duck-typed.
    """
    from datetime import date as _date

    # Read current cached state. Try L1 first; if L1 miss, peek at L2
    # (cheap — single SELECT). If both empty, there's nothing to patch.
    with _CACHE_LOCK:
        f = _CACHE.get(ticker)
    if f is None:
        try:
            from app.core.db import SessionLocal
            from app.services import fetch_cache_store
            with SessionLocal() as db:
                f = fetch_cache_store.read_fundamentals(db, ticker, _TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[fund] patch_finnhub L2 read failed for {ticker}: {exc}")
            return False
        if f is None:
            return False  # No prior fetch — let the next user request fetch fresh

    rec_date_str: str = rec.date.isoformat() if isinstance(rec.date, _date) else str(rec.date)
    existing_dates = {ep.date for ep in (f.earnings or [])}
    if rec_date_str in existing_dates:
        return False  # Already have this quarter — nothing to do

    surprise_pct: float | None = None
    if (
        rec.eps_actual is not None
        and rec.eps_estimate is not None
        and rec.eps_estimate != 0
    ):
        surprise_pct = (rec.eps_actual - rec.eps_estimate) / abs(rec.eps_estimate) * 100.0
    point = EarningsPoint(
        date=rec_date_str,
        eps_estimate=rec.eps_estimate,
        eps_reported=rec.eps_actual,
        surprise_pct=surprise_pct,
        revenue_estimate=rec.revenue_estimate,
        revenue_reported=rec.revenue_actual,
        time_utc=None,
    )
    f.earnings = (f.earnings or []) + [point]
    # Demote "upcoming" if it was pointing at this same date — and
    # update fetched_at so downstream TTL math treats this as fresh.
    if f.next_earnings_date == rec_date_str:
        f.next_earnings_date = None
        f.next_earnings_time_utc = None
        f.next_eps_estimate = None
        f.next_revenue_estimate = None
    f.fetched_at = time.time()

    # Write back to both cache layers. L1 first (fast); L2 second (durability).
    with _CACHE_LOCK:
        _CACHE[ticker] = f
    try:
        from app.core.db import SessionLocal
        from app.services import fetch_cache_store
        with SessionLocal() as db:
            fetch_cache_store.write_fundamentals(db, f)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[fund] patch_finnhub L2 write failed for {ticker}: {exc}")
    logger.info(
        f"[fund] {ticker}: injected earnings from Finnhub calendar "
        f"(date={rec_date_str} eps_actual={rec.eps_actual})"
    )
    return True


def _extract_micro(info: dict | None) -> MicroData:
    if not info:
        return MicroData()
    return MicroData(
        # Valuation multiples
        trailing_pe=_safe_float(info.get("trailingPE")),
        forward_pe=_safe_float(info.get("forwardPE")),
        peg_ratio=_safe_float(info.get("pegRatio")),
        trailing_peg_ratio=_safe_float(info.get("trailingPegRatio")),
        price_to_book=_safe_float(info.get("priceToBook")),
        price_to_sales=_safe_float(info.get("priceToSalesTrailing12Months")),
        enterprise_to_ebitda=_safe_float(info.get("enterpriseToEbitda")),
        enterprise_to_revenue=_safe_float(info.get("enterpriseToRevenue")),
        enterprise_value=_safe_float(info.get("enterpriseValue")),
        book_value=_safe_float(info.get("bookValue")),
        price_eps_current_year=_safe_float(info.get("priceEpsCurrentYear")),
        # Profitability / margins
        return_on_equity=_safe_float(info.get("returnOnEquity")),
        return_on_assets=_safe_float(info.get("returnOnAssets")),
        profit_margins=_safe_float(info.get("profitMargins")),
        operating_margins=_safe_float(info.get("operatingMargins")),
        gross_margins=_safe_float(info.get("grossMargins")),
        ebitda_margins=_safe_float(info.get("ebitdaMargins")),
        ebitda=_safe_float(info.get("ebitda")),
        gross_profits=_safe_float(info.get("grossProfits")),
        net_income_to_common=_safe_float(info.get("netIncomeToCommon")),
        # Earnings / EPS
        eps_trailing=_safe_float(
            info.get("trailingEps") or info.get("epsTrailingTwelveMonths")
        ),
        eps_forward=_safe_float(info.get("forwardEps") or info.get("epsForward")),
        eps_current_year=_safe_float(info.get("epsCurrentYear")),
        earnings_quarterly_growth=_safe_float(info.get("earningsQuarterlyGrowth")),
        # Revenue
        total_revenue=_safe_float(info.get("totalRevenue")),
        revenue_per_share=_safe_float(info.get("revenuePerShare")),
        # Leverage / liquidity
        debt_to_equity=_safe_float(info.get("debtToEquity")),
        current_ratio=_safe_float(info.get("currentRatio")),
        quick_ratio=_safe_float(info.get("quickRatio")),
        total_cash=_safe_float(info.get("totalCash")),
        total_cash_per_share=_safe_float(info.get("totalCashPerShare")),
        total_debt=_safe_float(info.get("totalDebt")),
        # Cash flow
        free_cashflow=_safe_float(info.get("freeCashflow")),
        operating_cashflow=_safe_float(info.get("operatingCashflow")),
        # Growth
        revenue_growth=_safe_float(info.get("revenueGrowth")),
        earnings_growth=_safe_float(info.get("earningsGrowth")),
        # Dividend
        dividend_rate=_safe_float(info.get("dividendRate")),
        dividend_yield=_safe_float(info.get("dividendYield")),
        five_year_avg_dividend_yield=_safe_float(info.get("fiveYearAvgDividendYield")),
        trailing_annual_dividend_rate=_safe_float(info.get("trailingAnnualDividendRate")),
        trailing_annual_dividend_yield=_safe_float(info.get("trailingAnnualDividendYield")),
        payout_ratio=_safe_float(info.get("payoutRatio")),
        # Beta / risk
        beta=_safe_float(info.get("beta")),
        # Shares / float / short interest
        shares_outstanding=_safe_float(info.get("sharesOutstanding")),
        float_shares=_safe_float(info.get("floatShares")),
        shares_short=_safe_float(info.get("sharesShort")),
        short_ratio=_safe_float(info.get("shortRatio")),
        short_percent_of_float=_safe_float(info.get("shortPercentOfFloat")),
        # Holdings
        held_percent_insiders=_safe_float(info.get("heldPercentInsiders")),
        held_percent_institutions=_safe_float(info.get("heldPercentInstitutions")),
        # Analyst aggregate
        recommendation_mean=_safe_float(info.get("recommendationMean")),
        number_of_analyst_opinions=_safe_float(info.get("numberOfAnalystOpinions")),
        # Performance vs market
        fifty_two_week_change=_safe_float(info.get("52WeekChange")),
        sp500_fifty_two_week_change=_safe_float(info.get("SandP52WeekChange")),
        # Governance / risk scores (Yahoo's 1-10 scales, lower = better)
        audit_risk=_safe_float(info.get("auditRisk")),
        board_risk=_safe_float(info.get("boardRisk")),
        compensation_risk=_safe_float(info.get("compensationRisk")),
        share_holder_rights_risk=_safe_float(info.get("shareHolderRightsRisk")),
        overall_risk=_safe_float(info.get("overallRisk")),
    )


def _growth(latest: float | None, prior: float | None) -> float | None:
    """Relative growth as a fraction: (latest - prior) / |prior|.

    Returns None when either side is missing or prior is zero (can't
    divide). Uses `abs(prior)` so the sign tracks the change direction
    consistently even across a loss→profit flip — same convention as
    `surprise_pct` elsewhere in this module and what yfinance's
    `earningsGrowth`/`revenueGrowth` fields encode (0.15 = +15%)."""
    if latest is None or prior is None or prior == 0:
        return None
    return (latest - prior) / abs(prior)


def _cagr_5y(series: list[tuple[str, float]]) -> float | None:
    """Annualized growth (CAGR) over ~5 years from a dated value series.

    `series`: (iso_date, value) tuples, oldest→newest. Picks the point
    closest to 5 years before the latest as the anchor, computes the
    exact year span from the dates, and returns
    `(latest/anchor)^(1/years) - 1` as a fraction.

    Returns None when:
      - fewer than 2 usable points,
      - the available span is < 2.5y (too short to call it a
        multi-year rate — a noisy 1y reading would masquerade as 5y),
      - either endpoint is <= 0 (CAGR is undefined across a sign
        flip / from a loss base; the YoY metric covers that regime).
    """
    from datetime import date as _date

    pts: list[tuple[_date, float]] = []
    for d_str, v in series:
        if v is None or v <= 0:
            continue
        try:
            pts.append((_date.fromisoformat(str(d_str)[:10]), float(v)))
        except (ValueError, TypeError):
            continue
    if len(pts) < 2:
        return None
    pts.sort(key=lambda t: t[0])
    latest_d, latest_v = pts[-1]
    target = latest_d.toordinal() - 1826  # ~5y in days
    anchor_d, anchor_v = min(
        pts[:-1], key=lambda t: abs(t[0].toordinal() - target)
    )
    years = (latest_d.toordinal() - anchor_d.toordinal()) / 365.25
    if years < 2.5 or anchor_v <= 0 or latest_v <= 0:
        return None
    try:
        return (latest_v / anchor_v) ** (1.0 / years) - 1.0
    except (ValueError, ZeroDivisionError):
        return None


def _grossly_diverges(provided: float, derived: float) -> bool:
    """True when a source-provided growth value is so far from the value
    we derive from our own reported-EPS/revenue series that showing it
    next to that series would break user trust.

    The canonical case: yfinance's `earningsGrowth` is computed off GAAP
    net income, which whipsaws when the prior-year base quarter was
    depressed by one-time items (merger amortization, restructuring,
    tax). GEN (post-Avast Gen Digital) shows +265% there while its
    smooth adjusted-EPS series (0.59→0.67) implies ~+14%. The two can't
    both sit in the same card.

    Heuristic (conservative — only fires on egregious mismatch):
      - opposite sign (one says growth, the other contraction), OR
      - magnitude off by > 3x with an absolute cushion so values near
        zero don't flap (0.20 vs 0.15 = normal noise, kept; 2.65 vs
        0.14 = ~19x = the GAAP-base artifact, overridden).
    """
    if (provided > 0) != (derived > 0) and abs(provided - derived) > 0.05:
        return True
    return abs(provided) > 3.0 * abs(derived) + 0.05


def _fy_growth_from_estimate_df(df: Any) -> float | None:
    """Extract the current-fiscal-year consensus growth from a yfinance
    `earnings_estimate` / `revenue_estimate` DataFrame.

    Those tables are indexed by period (`0q` / `+1q` / `0y` / `+1y`) with a
    `growth` column. The `0y` row's `growth` is the consensus CURRENT-FY
    growth — analyst full-year estimate (reported quarters + estimates for
    the quarters not yet reported) vs the prior-FY actual, as a fraction
    (e.g. 0.1734 = +17.3%). That is exactly the projected figure we want.

    Best-effort: returns None when the table is missing/empty, lacks the
    `0y` row or the `growth` column, or the value is NaN / non-numeric.
    Never raises.
    """
    try:
        if df is None or not hasattr(df, "loc") or getattr(df, "empty", False):
            return None
        if "growth" not in getattr(df, "columns", []):
            return None
        if "0y" not in df.index:
            return None
        return _safe_float(df.loc["0y", "growth"])
    except Exception:  # noqa: BLE001 — parse/shape failures are non-fatal
        return None


def _fy_growth_estimates(
    earnings_estimate: Any, revenue_estimate: Any
) -> tuple[float | None, float | None]:
    """Return (eps_curr_fy_growth, revenue_curr_fy_growth) read from the
    yfinance estimate DataFrames. Each is the `0y` row's `growth` (current-FY
    consensus growth, a fraction) or None when unavailable. Best-effort —
    swallows any parse/network artifact and degrades to (None, None)."""
    return (
        _fy_growth_from_estimate_df(earnings_estimate),
        _fy_growth_from_estimate_df(revenue_estimate),
    )


def _fy_avg_from_estimate_df(df: Any, period: str = "0y") -> float | None:
    """Extract a consensus AVERAGE from a yfinance `earnings_estimate` /
    `revenue_estimate` DataFrame — the given period row's `avg` column.
    `0y` = fiscal year in progress (the annual-table estimate row), `0q` =
    current quarter (fallback for the next-earnings estimate when the
    earnings_dates row carries none). Same shape tolerance as
    `_fy_growth_from_estimate_df`: never raises, None on any
    missing/empty/NaN condition."""
    try:
        if df is None or not hasattr(df, "loc") or getattr(df, "empty", False):
            return None
        if "avg" not in getattr(df, "columns", []):
            return None
        if period not in df.index:
            return None
        return _safe_float(df.loc[period, "avg"])
    except Exception:  # noqa: BLE001 — parse/shape failures are non-fatal
        return None


def _fill_growth_fallbacks(f: "Fundamentals") -> None:
    """Make the three growth metrics consistent with the EPS/revenue
    history shown in the same fundamentals card.

    The metrics (`earnings_growth` = EPS YoY, `earnings_quarterly_growth`
    = EPS QoQ, `revenue_growth` = Rev YoY) come from yfinance's `info`.
    Two failure modes this corrects:

    1. NULL — yfinance leaves them empty for non-US / thin-coverage
       tickers (e.g. UCG.MI) even though `earnings_dates` / quarterly
       statements give us the raw numbers. We derive + fill.

    2. MISLEADING — yfinance's `earningsGrowth` is GAAP-net-income
       based and explodes off a depressed prior-year base (GEN: +265%
       vs a +14% adjusted-EPS trend). When we can derive the growth
       from our own reported series AND yfinance's number grossly
       diverges from it, we prefer the derived value so the metric
       agrees with the EPS chart the user is looking at.

    Derivation:
    - EPS YoY:  latest reported quarter EPS vs 4 quarters back.
    - EPS QoQ:  latest reported quarter EPS vs the previous quarter.
    - Rev YoY:  latest quarter revenue vs 4 back. Prefers the clean
      `f.quarterly` statement; falls back to
      `f.earnings.revenue_reported` (Finnhub-backfilled).

    A source value within normal noise of the derived one is kept
    (yfinance is authoritative when sane). No-op on short history.
    """
    m = f.micro

    def _reconcile(provided: float | None, derived: float | None) -> float | None:
        """None-fill OR gross-divergence-correct, else keep provided."""
        if derived is None:
            return provided                 # can't derive → trust source
        if provided is None:
            return derived                  # source null → fill
        if _grossly_diverges(provided, derived):
            return derived                  # source absurd vs our series
        return provided                     # source sane → authoritative

    # EPS series: reported-only EarningsPoints, oldest→newest.
    eps_hist = [
        ep.eps_reported
        for ep in (f.earnings or [])
        if ep.eps_reported is not None
    ]

    qoq = _growth(eps_hist[-1], eps_hist[-2]) if len(eps_hist) >= 2 else None
    yoy = _growth(eps_hist[-1], eps_hist[-5]) if len(eps_hist) >= 5 else None

    before_q, before_y = m.earnings_quarterly_growth, m.earnings_growth
    m.earnings_quarterly_growth = _reconcile(m.earnings_quarterly_growth, qoq)
    m.earnings_growth = _reconcile(m.earnings_growth, yoy)

    # Revenue series — prefer the clean quarterly statement revenue,
    # fall back to earnings.revenue_reported (Finnhub-backfilled).
    # Keep dates alongside values for the 5y CAGR anchor.
    rev_dated = [
        (qp.fiscal_quarter_end, qp.revenue)
        for qp in (f.quarterly or [])
        if qp.revenue is not None
    ]
    if len(rev_dated) < 5:
        rev_dated = [
            (ep.date, ep.revenue_reported)
            for ep in (f.earnings or [])
            if ep.revenue_reported is not None
        ]
    rev_hist = [v for _, v in rev_dated]

    rev_yoy = _growth(rev_hist[-1], rev_hist[-5]) if len(rev_hist) >= 5 else None
    before_r = m.revenue_growth
    m.revenue_growth = _reconcile(m.revenue_growth, rev_yoy)

    # Revenue QoQ (new) — yfinance never provides this; always derive.
    if len(rev_hist) >= 2:
        m.revenue_quarterly_growth = _growth(rev_hist[-1], rev_hist[-2])

    # 5-year annualized CAGR (new) — EPS from the reported series,
    # revenue preferring the cleaner annual statement when available
    # (less noise than quarterly), else the quarterly/earnings series.
    eps_dated = [
        (ep.date, ep.eps_reported)
        for ep in (f.earnings or [])
        if ep.eps_reported is not None
    ]
    m.earnings_growth_5y = _cagr_5y(eps_dated)

    annual_rev = [
        (ap.fiscal_year_end, ap.revenue)
        for ap in (f.annual or [])
        if ap.revenue is not None
    ]
    m.revenue_growth_5y = _cagr_5y(annual_rev) or _cagr_5y(rev_dated)

    # Log only when we actually overrode a non-null source value (the
    # interesting case — a NULL-fill is routine and silent).
    corrected = []
    if before_y is not None and m.earnings_growth != before_y:
        corrected.append(f"EPS YoY {before_y:.3f}->{m.earnings_growth:.3f}")
    if before_q is not None and m.earnings_quarterly_growth != before_q:
        corrected.append(f"EPS QoQ {before_q:.3f}->{m.earnings_quarterly_growth:.3f}")
    if before_r is not None and m.revenue_growth != before_r:
        corrected.append(f"Rev YoY {before_r:.3f}->{m.revenue_growth:.3f}")
    if corrected:
        logger.info(
            f"[fund] {f.ticker}: reconciled growth vs reported-EPS "
            f"series ({', '.join(corrected)})"
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


def _transaction_type(text: str) -> str:
    """Coarse classifier for the transaction kind. Returns the leading
    descriptor stripped of price / parenthetical clauses, so same-day
    same-insider same-type rows can be coalesced even when yfinance
    splits a single trading event into multiple sub-orders at slightly
    different prices.

    Examples:
        "Sale at price 275.00 per share."       → "Sale"
        "Purchase at price 100.00"              → "Purchase"
        "Stock Award (Non Open Market)"         → "Stock Award"
        "Conversion of Exercise of security"    → "Conversion"
        "Sale"                                   → "Sale"
    """
    if not text:
        return ""
    s = text.strip()
    # Cut at the first delimiter that introduces price / parenthetical /
    # "of <details>" clauses. Anything before the cut is the type.
    for sep in (" at price ", " (", " of "):
        idx = s.find(sep)
        if idx > 0:
            return s[:idx].strip()
    return s


# Below this share count an insider transaction is considered noise:
# stock gifts to family members, director admin transfers, fractional
# share grants. The user explicitly asked to filter out "poche
# centinaia di azioni" — 500 is a generous floor that keeps any
# meaningful trade while pruning the editorial clutter (a CEO's
# 5-share split-adjusted dust transaction isn't market-relevant).
_INSIDER_MIN_SHARES = 500


def _extract_insiders(it_df: Any, limit: int = 10) -> list[InsiderTransaction]:
    """Read up to `limit` insider transactions, COALESCING multiple rows
    on the same date by the same insider with the same transaction type
    into a single line.

    Why coalesce: brokers split one trading-day's intent into several
    sub-orders (e.g. selling 50k shares as 5 × 10k partial fills at
    slightly different prices). yfinance returns each fill as a row,
    which clutters the UI and doesn't reflect the user-meaningful unit
    of analysis (the *event*).

    Coalesce key: (insider, date, transaction_type) — same person, same
    day, same type. Shares and dollar value are summed; the transaction
    label collapses to "<type> (<n> trades)" to make the merge visible.

    Significance filter: post-coalesce we drop entries with fewer than
    `_INSIDER_MIN_SHARES` total shares — at that scale the transaction
    is almost always a director admin move or a stock gift, not a
    market-relevant signal. This applies AFTER coalescing so the
    threshold is checked against the merged (summed) total, not the
    individual fills.
    """
    if it_df is None or it_df.empty:
        return []

    # Step 0: drop "ghost" rows. yfinance for some tickers (notably DDOG)
    # returns each insider transaction TWICE: once primary with full
    # Text + Value populated, once ghost with Text=NaN/empty + Value=NaN.
    # The ghost row has no incremental information and pollutes the UI
    # as a duplicate "AGARWAL AMIT — 20K" beneath the real "AGARWAL AMIT
    # Sale at price ... 20K · $2.6M". Drop them at parse time so the
    # rest of the pipeline only sees real events.
    raw: list[InsiderTransaction] = []
    for _, row in it_df.iterrows():
        text_v = row.get("Text")
        text_s = "" if text_v is None or (isinstance(text_v, float) and pd.isna(text_v)) else str(text_v).strip()
        txn_v = row.get("Transaction")
        txn_s = "" if txn_v is None or (isinstance(txn_v, float) and pd.isna(txn_v)) else str(txn_v).strip()
        value_raw = row.get("Value")
        value_is_missing = (
            value_raw is None
            or (isinstance(value_raw, float) and pd.isna(value_raw))
            or _safe_float(value_raw) in (None, 0.0)
        )
        # Ghost-row condition: no human-readable description AND no dollar
        # value. Real "Stock Gift at price 0.00" rows have Text populated
        # so they survive (Value=0 is fine when Text is meaningful).
        if not text_s and not txn_s and value_is_missing:
            continue

        date_v = row.get("Start Date")
        date_s = (
            str(date_v.date())
            if hasattr(date_v, "date")
            else str(date_v)
            if date_v is not None
            else ""
        )
        raw.append(InsiderTransaction(
            insider=str(row.get("Insider") or "").strip(),
            position=str(row.get("Position") or "").strip(),
            transaction=text_s or txn_s,
            date=date_s,
            shares=_safe_int(row.get("Shares")),
            value=_safe_float(row.get("Value")),
        ))

    # Step 2: group by (insider, date, type), preserving first-occurrence
    # order so the most recent rows (yfinance returns DESC) stay first.
    grouped: dict[tuple[str, str, str], list[InsiderTransaction]] = {}
    order: list[tuple[str, str, str]] = []
    for tx in raw:
        ttype = _transaction_type(tx.transaction)
        key = (tx.insider, tx.date, ttype)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(tx)

    # Step 3: collapse each group into one entry. Single-entry groups
    # pass through unchanged; multi-entry groups sum shares + value
    # and rewrite the transaction label.
    out: list[InsiderTransaction] = []
    for key in order:
        group = grouped[key]
        if len(group) == 1:
            out.append(group[0])
            continue
        insider, date, ttype = key
        total_shares = sum((t.shares or 0) for t in group)
        total_value = sum((t.value or 0.0) for t in group)
        # Use the first non-empty position from the group (typically all
        # match, but be defensive).
        position = next((t.position for t in group if t.position), "")
        # Merged label: "Sale (3 trades)" makes the aggregation visible
        # so the user knows we're showing a sum, not a single fill.
        merged_label = (
            f"{ttype} ({len(group)} trades)"
            if ttype
            else group[0].transaction
        )
        out.append(InsiderTransaction(
            insider=insider,
            position=position,
            transaction=merged_label,
            date=date,
            shares=total_shares if total_shares > 0 else None,
            value=total_value if total_value > 0 else None,
        ))

    # Step 4: significance filter. Drop transactions where the
    # post-coalesce share count is under the noise threshold. NB: we
    # check shares (not value) because stock-gift transactions have
    # value=0 by yfinance convention but are still editorially
    # meaningless when shares are tiny.
    out = [t for t in out if (t.shares or 0) >= _INSIDER_MIN_SHARES]

    # Step 5: cap to limit AFTER coalescing + filtering so we return up
    # to `limit` *significant* events (not raw fills, not noise dust).
    return out[:limit]


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


def _extract_actions(df: Any, limit: int = 12, *, scale: float = 1.0) -> list[AnalystAction]:
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
        if cur_pt is not None:
            cur_pt *= scale
        if prior_pt is not None:
            prior_pt *= scale
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


def _extract_price_target(pt: Any, *, scale: float = 1.0) -> AnalystPriceTarget:
    if not pt or not isinstance(pt, dict):
        return AnalystPriceTarget(current=None, low=None, mean=None, median=None, high=None)
    def _s(v: Any) -> float | None:
        f = _safe_float(v)
        return f * scale if f is not None else None
    return AnalystPriceTarget(
        current=_s(pt.get("current")),
        low=_s(pt.get("low")),
        mean=_s(pt.get("mean")),
        median=_s(pt.get("median")),
        high=_s(pt.get("high")),
    )


# ── yfinance raw-call helpers ─────────────────────────────────────────────────

from app.core.errors import RateLimitError, UpstreamTimeout, UpstreamUnavailable  # noqa: E402
from app.services._retry import with_backoff  # noqa: E402


def _normalize_yf_error(exc: Exception) -> Exception:
    """Map yfinance/requests exceptions into our typed UpstreamError hierarchy.
    The retry decorator only retries the typed errors it knows about.

    Classification order:
    1. Exception type check (TimeoutError, requests.Timeout, etc.)
    2. Message keyword check (for yfinance-specific error strings)
    3. Fallback to UpstreamUnavailable (non-retryable)
    """
    # Type-based check first — catches TimeoutError / requests.Timeout / socket.timeout
    # regardless of message text.
    try:
        import socket
        timeout_types: tuple[type[BaseException], ...] = (TimeoutError, socket.timeout)
    except ImportError:
        timeout_types = (TimeoutError,)
    try:
        import requests
        timeout_types = timeout_types + (requests.Timeout,)
    except ImportError:
        pass
    if isinstance(exc, timeout_types):
        return UpstreamTimeout(str(exc), source="yfinance", op="fundamentals")

    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg or "too many" in msg:
        return RateLimitError(str(exc), source="yfinance", op="fundamentals")
    if "timeout" in msg or "timed out" in msg:
        return UpstreamTimeout(str(exc), source="yfinance", op="fundamentals")
    return UpstreamUnavailable(str(exc), source="yfinance", op="fundamentals")


def _do_yf_call(ticker: str) -> dict:
    """Issue all yfinance sub-requests for a single ticker and return the raw
    results as a plain dict keyed by endpoint name.  Each endpoint is wrapped
    in its own try/except so a 404 on one (e.g. insider_transactions for EU
    stocks) does not blank out the others.

    This function is the single wrapping point for the retry decorator: if
    ANY top-level exception escapes (i.e. is not caught by a per-endpoint
    block), the decorator decides whether to re-raise or retry.  Per-endpoint
    failures are returned as None values so the caller can detect partial
    payloads.
    """
    import yfinance as yf

    t = yf.Ticker(ticker)
    out: dict = {
        "income_stmt": None,
        "quarterly_income_stmt": None,
        "earnings_dates": None,
        "info": None,
        "insider_transactions": None,
        "recommendations": None,
        "analyst_price_targets": None,
        "upgrades_downgrades": None,
        "earnings_estimate": None,
        "revenue_estimate": None,
    }
    try:
        out["income_stmt"] = t.income_stmt
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] income_stmt {ticker}: {exc}")
    try:
        out["quarterly_income_stmt"] = t.quarterly_income_stmt
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] quarterly_income_stmt {ticker}: {exc}")
    try:
        out["earnings_dates"] = t.earnings_dates
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] earnings_dates {ticker}: {exc}")
    try:
        out["info"] = t.get_info()
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] info {ticker}: {exc}")
    try:
        out["insider_transactions"] = t.insider_transactions
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] insider_transactions {ticker}: {exc}")
    try:
        out["recommendations"] = t.recommendations
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] recommendations {ticker}: {exc}")
    try:
        out["analyst_price_targets"] = t.analyst_price_targets
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] analyst_price_targets {ticker}: {exc}")
    try:
        out["upgrades_downgrades"] = t.upgrades_downgrades
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] upgrades_downgrades {ticker}: {exc}")
    try:
        out["earnings_estimate"] = t.earnings_estimate
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] earnings_estimate {ticker}: {exc}")
    try:
        out["revenue_estimate"] = t.revenue_estimate
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            raise normalized from exc
        logger.debug(f"[fund] revenue_estimate {ticker}: {exc}")
    return out


@with_backoff(
    retries=3,
    base_delay=0.5,
    max_delay=4.0,
    on=(UpstreamTimeout, RateLimitError),
)
def _yf_fetch_with_retry(ticker: str) -> dict:
    """Wrapping point: chiamata yfinance + normalizzazione errori.

    Per-endpoint timeouts and rate-limit errors are re-raised from
    ``_do_yf_call`` (as ``UpstreamTimeout`` / ``RateLimitError``) so the
    ``@with_backoff`` decorator retries them.  Other per-endpoint exceptions
    (e.g. malformed payload causing ``KeyError`` / ``ValueError``) are swallowed
    inside ``_do_yf_call`` and degrade gracefully to ``None`` for that key —
    they do NOT trigger a retry.

    Each retryable failure ALSO informs ``yfinance_health`` so the circuit
    breaker converges as designed (5 failures → OPEN within WINDOW_SECONDS).
    Without this, the @with_backoff decorator would hide intermediate
    failures and the breaker would only see the final retry-exhausted
    exception — a single user call could consume up to 4 raw upstream
    failures while contributing only 1 to the threshold, making the
    breaker open ~4x slower than designed."""
    from app.services import yfinance_health
    try:
        return _do_yf_call(ticker)
    except Exception as exc:  # noqa: BLE001
        normalized = _normalize_yf_error(exc)
        if isinstance(normalized, (RateLimitError, UpstreamTimeout)):
            yfinance_health.record_failure(f"fundamentals {ticker}: {exc}")
        raise normalized from exc


# ── fetch orchestration ───────────────────────────────────────────────────────

# Min-interval throttle on REAL upstream fetches (rate-limit insurance).
#
# Rationale: `score_service.recompute_all` iterates ~1049 stocks and, on a
# cold/expired fundamentals cache, can fire thousands of sequential yfinance
# sub-requests back-to-back with no spacing — the single biggest source of
# 429/ban risk in the app (see the data-source audit). Throttling HERE (the
# fresh-fetch choke point, reached only on an L1+L2 cache MISS) rather than in
# the recompute loop means:
#   - warm-cache runs pay ZERO (cache hits never enter this function), so the
#     normal post-scan recompute + the manual "Ricalcola score" stay fast;
#   - EVERY caller is protected (detail page, sector pre-pass, scoring loop…),
#     not just one loop;
#   - an ISOLATED fetch after idle doesn't wait at all — only back-to-back
#     bursts get spaced to >= _MIN_FETCH_INTERVAL apart.
_MIN_FETCH_INTERVAL = 0.15  # seconds between consecutive upstream fetches
_FETCH_GATE_LOCK = Lock()
_last_fetch_monotonic = 0.0


def _throttle_upstream_fetch() -> None:
    """Block until >= _MIN_FETCH_INTERVAL (plus small jitter) has elapsed since
    the previous upstream fetch, so a tight loop can't burst Yahoo. No-op for
    isolated calls (idle longer than the interval)."""
    global _last_fetch_monotonic
    with _FETCH_GATE_LOCK:
        now = time.monotonic()
        wait = _MIN_FETCH_INTERVAL - (now - _last_fetch_monotonic)
        if wait > 0:
            # Jitter avoids a lock-step cadence that some WAFs flag as botlike.
            time.sleep(wait + random.uniform(0.0, 0.05))
        _last_fetch_monotonic = time.monotonic()


def _fetch_fresh(ticker: str) -> Fundamentals:
    from app.services import yfinance_health

    f = Fundamentals(ticker=ticker, fetched_at=time.time())

    if yfinance_health.is_open():
        f.error = "yfinance circuit breaker is open (rate-limited); try again later"
        logger.info(f"[fundamentals] breaker OPEN — returning empty payload for {ticker}")
        return f

    # Space out real upstream fetches (cache miss only — see _throttle docstring).
    _throttle_upstream_fetch()

    saw_success = False
    def _maybe_record(exc: Exception | None) -> None:
        if exc is None:
            return
        if yfinance_health.is_rate_limit_error(exc):
            yfinance_health.record_failure(f"fundamentals {ticker}: {exc}")

    try:
        raw = _yf_fetch_with_retry(ticker)
        # Each of these is independently network-bound and may individually
        # fail; _do_yf_call returns None for each failed endpoint.
        try:
            f.annual = _extract_annual(raw.get("income_stmt"))
            if f.annual:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] annual {ticker}: {e}")
            _maybe_record(e)
        try:
            f.quarterly = _extract_quarterly(raw.get("quarterly_income_stmt"))
            if f.quarterly:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] quarterly {ticker}: {e}")
            _maybe_record(e)
        try:
            hist, nxt_date, nxt_est, nxt_rev_est, nxt_time = _extract_earnings(raw.get("earnings_dates"))
            f.earnings = hist
            f.next_earnings_date = nxt_date
            f.next_earnings_time_utc = nxt_time
            f.next_eps_estimate = nxt_est
            f.next_revenue_estimate = nxt_rev_est
            if hist or nxt_date:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] earnings {ticker}: {e}")
            _maybe_record(e)
        # Finnhub fallback — patches the most recent earnings actuals when
        # yfinance hasn't ingested them yet (typical lag: 1-3h post
        # release; Finnhub: ~30min). Only kicks in when:
        #  (a) FINNHUB_API_KEY is set
        #  (b) yfinance left a "next event" with date in the past (=
        #      release happened but yfinance hasn't scraped the actual)
        # Cheap to call — one HTTP roundtrip per ticker, on the upstream
        # path only (so behind the same 7d TTL gate as the rest of the
        # fundamentals payload). Failures are silent — Finnhub down just
        # means we keep yfinance's slower data.
        try:
            _merge_finnhub_actuals_into_earnings(ticker, f)
        except Exception as e:
            logger.debug(f"[fund] finnhub merge {ticker}: {e}")
        # Revenue backfill — yfinance never provides revenue in
        # earnings_dates, so without this the revenue columns are
        # always blank. One per-symbol Finnhub call, behind the 7d
        # fundamentals TTL. Failures silent (Finnhub down → no revenue
        # this cycle, filled next refresh).
        try:
            _merge_finnhub_revenue(ticker, f)
        except Exception as e:
            logger.debug(f"[fund] finnhub revenue merge {ticker}: {e}")
        # LSE listings quote in PENCE (currency GBp/GBX). yfinance's analyst
        # price targets come back in that SAME unit while our quote/chart
        # paths normalize prices to POUNDS — unscaled, the analyst card
        # showed a "4276" target next to a 39.40 price (HLMA.L, 2026-06-11).
        # Applied to the yfinance-sourced target extractions below; the
        # Nasdaq fallback is untouched (US source, already major units).
        pence_scale = 1.0
        try:
            # Single info() call — both micro fundamentals and the company
            # profile come from the same dict, so pulling them together
            # avoids a duplicate slow-endpoint roundtrip.
            info = raw.get("info")
            f.micro = _extract_micro(info)
            f.profile = _extract_profile(info)
            if isinstance(info, dict) and is_minor_unit(info.get("currency")):
                pence_scale = 0.01
            if any(getattr(f.micro, k) is not None for k in vars(f.micro)):
                saw_success = True
            if f.profile.long_business_summary or f.profile.website:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] info {ticker}: {e}")
            _maybe_record(e)
        # Current-FY projected growth — read the consensus `0y` growth from
        # yfinance's earnings_estimate / revenue_estimate tables. Stored raw
        # on micro for transparency; the prefer-logic below promotes them
        # over the trailing-YoY figure. Best-effort (the helper swallows
        # missing/empty/NaN tables → None) so it never blocks the build.
        try:
            eps_fy, rev_fy = _fy_growth_estimates(
                raw.get("earnings_estimate"), raw.get("revenue_estimate")
            )
            f.micro.eps_growth_curr_fy = eps_fy
            f.micro.revenue_growth_curr_fy = rev_fy
            # Same tables, `avg` column: the full-year consensus VALUES for
            # the FY in progress — the estimate row of the annual table.
            f.curr_fy_eps_estimate = _fy_avg_from_estimate_df(
                raw.get("earnings_estimate")
            )
            f.curr_fy_revenue_estimate = _fy_avg_from_estimate_df(
                raw.get("revenue_estimate")
            )
            # Next-quarter fallback: when the earnings_dates "next up" row
            # carries no estimates (thin coverage / orphan calendar rows),
            # fill from the same estimate tables' `0q` consensus so the
            # PROSSIMA row isn't a strip of dashes while the annual row
            # right below shows a full-year figure.
            if f.next_earnings_date is not None:
                if f.next_eps_estimate is None:
                    f.next_eps_estimate = _fy_avg_from_estimate_df(
                        raw.get("earnings_estimate"), period="0q"
                    )
                if f.next_revenue_estimate is None:
                    f.next_revenue_estimate = _fy_avg_from_estimate_df(
                        raw.get("revenue_estimate"), period="0q"
                    )
        except Exception as e:
            logger.debug(f"[fund] fy-growth estimates {ticker}: {e}")
        # Growth fallback — derive EPS YoY/QoQ + Rev YoY from the
        # historical series when yfinance's `info` left them null
        # (common for non-US / thin-coverage tickers). Runs AFTER
        # _extract_micro (so we know what yfinance gave) and after
        # earnings/quarterly are populated. Pure in-memory, no I/O.
        try:
            _fill_growth_fallbacks(f)
        except Exception as e:
            logger.debug(f"[fund] growth fallback {ticker}: {e}")
        # Prefer the current-FY PROJECTION over trailing YoY. Runs AFTER the
        # reconcile pass so the projection wins: the projected figure is
        # estimates-inclusive (reported quarters + consensus for the not-yet-
        # reported quarters vs prior-FY actual) and is the metric the Growth
        # scoring pillar should grade on. The reconciled trailing-YoY value
        # remains the fallback whenever the projection is unavailable.
        # Overwriting micro.{earnings,revenue}_growth here means BOTH the
        # per-stock Growth components AND the sector medians (aggregated from
        # these same fields by sector_stats_service) use the projected figure
        # automatically — apples-to-apples, with no score_service change.
        if f.micro.eps_growth_curr_fy is not None:
            f.micro.earnings_growth = f.micro.eps_growth_curr_fy
        if f.micro.revenue_growth_curr_fy is not None:
            f.micro.revenue_growth = f.micro.revenue_growth_curr_fy
        try:
            # Pull more candidates upstream than the UI shows because the
            # significance filter can drop a chunk of rows (gifts, admin
            # micro-transfers). 25 in → after filter the UI's slice(0,10)
            # still has 10 real events for most tickers.
            f.insiders = _extract_insiders(raw.get("insider_transactions"), limit=25)
            if f.insiders:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] insiders {ticker}: {e}")
            _maybe_record(e)
        try:
            f.analyst_ratings = _extract_ratings(raw.get("recommendations"))
            if f.analyst_ratings:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] recommendations {ticker}: {e}")
            _maybe_record(e)
        # Finnhub fallback for aggregated ratings buckets — yfinance's
        # `recommendations` table is stale at source for an expanding
        # subset of names (the same dead-feed pattern that killed
        # `upgrades_downgrades`). When yfinance returns zero buckets,
        # ask Finnhub. Same shape, same dataclass — just hot-swapped.
        if not f.analyst_ratings:
            try:
                from app.services import finnhub_news_service
                trend = finnhub_news_service.fetch_recommendation_trend(ticker)
                if trend:
                    f.analyst_ratings = [
                        AnalystRating(
                            period=b.period,
                            strong_buy=b.strong_buy,
                            buy=b.buy,
                            hold=b.hold,
                            sell=b.sell,
                            strong_sell=b.strong_sell,
                        )
                        for b in trend
                    ]
                    saw_success = True
                    logger.debug(
                        f"[fund] {ticker}: yfinance ratings empty, "
                        f"filled {len(trend)} buckets from Finnhub fallback"
                    )
            except Exception as e:  # noqa: BLE001 — fallback is non-fatal
                logger.debug(f"[fund] finnhub recommendation fallback {ticker}: {e}")
        # Tier-3 fallback: Nasdaq's key-less consensus. Reached only when
        # BOTH yfinance and Finnhub came up empty (e.g. Finnhub breaker
        # open) — an independent provider so the buckets survive a
        # Finnhub outage. Nasdaq has no strong-buy/strong-sell split
        # (those map to 0). One fetch is 24h-cached and ALSO serves the
        # price-target fallback below.
        if not f.analyst_ratings:
            try:
                from app.services import nasdaq_analyst_service
                na = nasdaq_analyst_service.fetch_analyst(ticker)
                if na and na.buckets:
                    f.analyst_ratings = [
                        AnalystRating(
                            period=b.period,
                            strong_buy=b.strong_buy,
                            buy=b.buy,
                            hold=b.hold,
                            sell=b.sell,
                            strong_sell=b.strong_sell,
                        )
                        for b in na.buckets
                    ]
                    saw_success = True
                    logger.debug(
                        f"[fund] {ticker}: yfinance+Finnhub ratings empty, "
                        f"filled {len(na.buckets)} buckets from Nasdaq fallback"
                    )
            except Exception as e:  # noqa: BLE001 — fallback is non-fatal
                logger.debug(f"[fund] nasdaq ratings fallback {ticker}: {e}")
        try:
            f.price_target = _extract_price_target(raw.get("analyst_price_targets"), scale=pence_scale)
            if f.price_target.mean is not None:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] price_target {ticker}: {e}")
            _maybe_record(e)
        # Tier-3 fallback for the price target: when yfinance left it
        # empty, borrow Nasdaq's consensus spread (low/high/mean). The
        # fetch is the SAME 24h-cached call the ratings fallback used, so
        # this is free when ratings already triggered it.
        if f.price_target.mean is None:
            try:
                from app.services import nasdaq_analyst_service
                na = nasdaq_analyst_service.fetch_analyst(ticker)
                if na and na.pt_mean is not None:
                    f.price_target = AnalystPriceTarget(
                        current=None,
                        low=na.pt_low,
                        mean=na.pt_mean,
                        median=na.pt_mean,  # Nasdaq exposes no separate median
                        high=na.pt_high,
                    )
                    saw_success = True
                    logger.debug(
                        f"[fund] {ticker}: yfinance price-target empty, "
                        f"filled from Nasdaq fallback (mean={na.pt_mean})"
                    )
            except Exception as e:  # noqa: BLE001 — fallback is non-fatal
                logger.debug(f"[fund] nasdaq price-target fallback {ticker}: {e}")
        try:
            f.analyst_actions = _extract_actions(raw.get("upgrades_downgrades"), scale=pence_scale)
            if f.analyst_actions:
                saw_success = True
        except Exception as e:
            logger.debug(f"[fund] upgrades_downgrades {ticker}: {e}")
            _maybe_record(e)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fundamentals] top-level failure for {ticker}: {e}")
        f.error = str(e)
        # NOTE: no `record_failure` here — `_yf_fetch_with_retry` already
        # records each retry attempt to the breaker, so an additional
        # record here would double-count and trip the breaker too fast
        # on a single user-call exhaustion.
    # Partial-fetch detection: when the slow `Ticker.info` call fails
    # (rate-limited / yfinance backoff) the payload survives without a
    # top-level exception — annual/quarterly may be populated, but micro
    # and profile are completely empty. Persisting that to L2 would mask
    # a UI-visible failure for 24h ("Profilo Società" + "Valutazione"
    # cards both blank). Mark it as a recoverable error so the L2 write
    # in `get_fundamentals` is skipped and the next request retries.
    info_seen = (
        any(getattr(f.micro, k) is not None for k in vars(f.micro))
        or bool(f.profile.long_business_summary)
        or bool(f.profile.website)
    )
    if not info_seen and not f.error:
        f.error = "info endpoint returned no data — partial fetch"
        logger.info(
            f"[fundamentals] {ticker}: partial fetch (info empty) — "
            "skipping L2 persist; next request will retry"
        )
    # Per-source metrics: count this fetch attempt
    from app.services import data_source_metrics
    if saw_success and not f.error:
        yfinance_health.record_success()
        data_source_metrics.record_success("yfinance", "fundamentals")
    else:
        data_source_metrics.record_failure(
            "yfinance", "fundamentals",
            reason=f.error or f"empty payload for {ticker}",
        )
    return f


def get_fundamentals_cached(db, ticker: str) -> "Fundamentals | None":
    """CACHE-ONLY fundamentals read for the signal scan: L1 then L2, never an
    upstream fetch (the scan touches ~900 stocks; a fetch storm is unacceptable).
    Returns None on a cache miss - that stock simply gets no non-technical events."""
    f = _CACHE.get(ticker)
    if f is not None:
        return f
    from app.services import fetch_cache_store
    from_db = fetch_cache_store.read_fundamentals(db, ticker, _TTL_SECONDS)
    if from_db is not None:
        _CACHE[ticker] = from_db
        return from_db
    return None


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

    def _is_cached_fresh(c: Fundamentals) -> bool:
        """TTL check that respects the negative-cache: error payloads use
        the shorter `_NEGATIVE_TTL_SECONDS` so they re-attempt sooner."""
        ttl = _NEGATIVE_TTL_SECONDS if c.error else _TTL_SECONDS
        return (now - c.fetched_at) < ttl

    if not force_refresh:
        # L1
        with _CACHE_LOCK:
            cached = _CACHE.get(ticker)
            if cached is not None and _is_cached_fresh(cached):
                return cached
        # L2 — try DB. Imported lazily to avoid an import cycle (the
        # store module imports the dataclasses defined above).
        try:
            from app.core.db import SessionLocal
            from app.services import fetch_cache_store
            with SessionLocal() as db:
                # Pass the LONGER TTL so the DB read returns even error
                # rows (TTL is enforced ticker-by-ticker in code below).
                # The _is_cached_fresh check then enforces the shorter
                # negative-cache TTL on error payloads.
                from_db = fetch_cache_store.read_fundamentals(
                    db, ticker, _TTL_SECONDS
                )
            if from_db is not None and _is_cached_fresh(from_db):
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
    #
    # Negative-cache rule: persist BOTH success rows AND permanent-error
    # rows (404 / no-data / delisted) to L2. The L2 read above gates
    # error rows by the shorter `_NEGATIVE_TTL_SECONDS`, so they refresh
    # sooner than success rows. Transient errors (rate-limit, breaker)
    # are still skipped — caching them would just delay yfinance recovery.
    should_persist = not fresh.error or _is_permanent_error(fresh.error)
    if should_persist:
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


def hydrate_l1_from_db() -> tuple[int, int]:
    """Populate the in-memory L1 cache from the persistent L2 table. Call
    once at app startup so the first request after a restart hits L1
    instantly instead of round-tripping the DB per ticker.

    Returns:
        (loaded, skipped) — loaded is the number of fresh entries hydrated;
        skipped is the count of rows that failed deserialization or schema
        validation (corrupt / old-schema rows)."""
    try:
        from app.core.db import SessionLocal
        from app.services import fetch_cache_store
        with SessionLocal() as db:
            entries, skipped = fetch_cache_store.hydrate_all_fundamentals(db, _TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[fund] L1 hydration failed: {exc}")
        return 0, 0
    with _CACHE_LOCK:
        _CACHE.update(entries)
    loaded = len(entries)
    if loaded or skipped:
        logger.info(f"[fund] hydrated L1 with {loaded} entries from L2 (skipped {skipped})")
    return loaded, skipped
