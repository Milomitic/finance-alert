"""Sector recap endpoints - /api/sectors and /api/sectors/{name}/detail.

Powers the SectorDetailPage UI: when a user clicks a sector tile in
the dashboard heatmap (or the sector badge on a stock card), they
land on a page showing peer stocks + aggregate stats for that
sector. Mirrors the role indices play via /stocks?index=CODE.

The /overview endpoint (added May 2026 for the Sectors hub at /sectors)
is the FAST sibling — SQL aggregates + a TTL-cached payload, with the
fundamentals medians coming from the already-warm L1 cache only
(never a fresh fetch). Cold tickers contribute nothing to the median
rather than triggering a network call. The detail endpoint
(`{name}/detail`) keeps the full slow path for the per-sector page
where the user already paid the navigation cost.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.visibility import visible_country_clause
from app.models import (
    Alert,
    MarketSnapshot,
    ScoreHistory,
    Stock,
    StockScore,
    TechnicalScore,
    User,
)
from app.services import sectors_overview_cache, stock_fundamentals_service
from app.services.sectors_overview_cache import (
    clear_overview_cache,  # noqa: F401 — re-export for tests/back-compat
)

router = APIRouter(prefix="/api/sectors", tags=["sectors"])


# GICS sector → SPDR sector-ETF proxy. Static by design (the 11 Select
# Sector SPDRs are a fixed, well-known family); which of these actually
# appear on a tile is decided at request time by `_etf_proxies`, which
# checks the CATALOG — a mapped ticker missing from `stocks` renders no
# link rather than a dead /stocks/XLRE 404.
SECTOR_ETF_PROXY: dict[str, str] = {
    "Energy": "XLE",
    "Financials": "XLF",
    "Information Technology": "XLK",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}


class SectorTrendPoint(BaseModel):
    """One point of the per-sector Qualità score sparkline: the average
    composite across the sector's stocks on one `score_history` capture day."""
    date: str  # ISO captured_on
    avg: float


class SectorSummary(BaseModel):
    name: str
    stock_count: int
    avg_score: float | None
    median_pe: float | None
    median_pb: float | None
    median_roe: float | None
    median_dividend_yield: float | None
    # ── Overview enrichments (ESP-2) ─────────────────────────────────
    # All defaulted so the legacy GET /api/sectors (bare `_sector_rollup`)
    # keeps validating without paying for the extra queries — only the
    # /overview endpoint populates them (inside its 60s TTL cache).
    # Tecnico lens: avg technical composite + how many stocks carry one.
    avg_technical: float | None = None
    technical_count: int = 0
    # Δ% giornaliero — read from the latest market snapshot's `sectors`
    # block (same aggregation the dashboard heatmap shows), NOT recomputed.
    change_pct: float | None = None
    # Segnali negli ultimi 7 giorni (signal_date-based, non-archived).
    signals_7d: int = 0
    signals_7d_bull: int = 0
    signals_7d_bear: int = 0
    # SPDR proxy ticker, only when present in the catalog (else None).
    etf_proxy: str | None = None
    # Qualità score trend (last ~30 score_history captures, ascending).
    score_trend: list[SectorTrendPoint] = Field(default_factory=list)


class IndustryRow(BaseModel):
    """One row in the overview's industry table.

    Cheap to compute: a single SQL aggregate over `stock_scores` + `stocks`
    gives stock_count + avg_composite without any per-ticker yfinance
    cache hits. The richer fundamentals medians are deliberately omitted
    here — they require the slow per-ticker loop and the hub page only
    needs the score breadth.
    """
    name: str
    sector: str | None
    stock_count: int
    avg_score: float | None


class SectorsOverviewOut(BaseModel):
    """Aggregated payload for the /sectors hub page.

    Returns everything the page needs in one request: summary counts,
    per-sector rollups (reusing the existing SectorSummary shape so the
    detail-page tile cards stay consistent), and a flat industries
    table for the secondary breakdown.

    The fundamentals medians (PE/PB/ROE/dividend yield) come from the
    per-ticker loop in `/api/sectors`, which is reused — see `_sector_rollup`.
    """
    total_stocks: int
    total_sectors: int
    total_industries: int
    sectors: list[SectorSummary]
    industries: list[IndustryRow]


class SectorStockRow(BaseModel):
    ticker: str
    name: str | None
    country: str | None
    industry: str | None
    market_cap: float | None
    composite: float | None
    quality: float | None  # legacy V3.1 alias
    profitability: float | None
    sustainability: float | None
    growth: float | None
    value: float | None
    momentum: float | None
    sentiment: float | None
    risk_tier: str | None
    pe: float | None
    pb: float | None
    roe: float | None
    revenue_growth: float | None
    profit_margin: float | None
    dividend_yield: float | None


class CountBucket(BaseModel):
    label: str
    count: int


class PillarAverages(BaseModel):
    profitability: float | None
    sustainability: float | None
    growth: float | None
    value: float | None
    momentum: float | None
    sentiment: float | None


class SectorKpis(BaseModel):
    stock_count: int
    avg_composite: float | None
    median_composite: float | None
    # Tecnico lens: avg technical composite across the sector's stocks
    # that have one (+ the count, so the UI can qualify the average).
    avg_technical: float | None = None
    technical_count: int = 0
    median_pe: float | None
    median_pb: float | None
    median_roe: float | None
    median_revenue_growth: float | None
    median_profit_margin: float | None
    median_dividend_yield: float | None
    median_market_cap: float | None
    score_distribution: list[int]
    pillar_averages: PillarAverages
    industry_breakdown: list[CountBucket]
    country_distribution: list[CountBucket]
    risk_distribution: list[CountBucket]
    market_cap_distribution: list[CountBucket]


class SectorDetailOut(BaseModel):
    sector: str
    kpis: SectorKpis
    top_picks: list[SectorStockRow]
    bottom_picks: list[SectorStockRow]
    stocks: list[SectorStockRow]


def _is_finite(x):
    if x is None:
        return False
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def _safe_median(values):
    finite = [float(v) for v in values if v is not None and _is_finite(v)]
    if not finite:
        return None
    return float(statistics.median(finite))


def _safe_mean(values):
    finite = [float(v) for v in values if v is not None and _is_finite(v)]
    if not finite:
        return None
    return sum(finite) / len(finite)


def _normalise_div_yield(v):
    if v is None or not _is_finite(v) or v < 0:
        return None
    return v if v > 1 else v * 100.0


def _to_pct(v):
    if v is None or not _is_finite(v):
        return None
    return v * 100.0


def _build_stock_row(stock, score):
    # L1-only fundamentals lookup: read directly from the in-memory
    # `_CACHE` dict. Cold tickers fall back to None for PE/PB/ROE/etc
    # rather than triggering a network fetch — the sector detail
    # endpoint used to iterate `get_fundamentals(ticker)` per stock,
    # which on cold caches or open yfinance circuits could spend 50+
    # seconds on a single 150-stock sector (Information Technology was
    # the canonical victim, May 2026). L1 is hydrated from L2 at
    # startup (~978 entries on this catalog) so warm coverage is >85%.
    pe = pb = roe = rev_g = pm = dy = None
    funds = stock_fundamentals_service._CACHE.get(stock.ticker)  # noqa: SLF001
    if funds is not None and funds.micro is not None:
        m = funds.micro
        pe = m.trailing_pe if _is_finite(m.trailing_pe) else None
        pb = m.price_to_book if _is_finite(m.price_to_book) else None
        roe = _to_pct(m.return_on_equity)
        rev_g = _to_pct(m.revenue_growth)
        pm = _to_pct(m.profit_margins)
        dy = _normalise_div_yield(m.dividend_yield)
    return SectorStockRow(
        ticker=stock.ticker,
        name=stock.name,
        country=stock.country,
        industry=stock.industry,
        market_cap=float(stock.market_cap) if stock.market_cap else None,
        composite=score.composite if score else None,
        quality=score.quality if score else None,
        profitability=score.profitability if score else None,
        sustainability=score.sustainability if score else None,
        growth=score.growth if score else None,
        value=score.value if score else None,
        momentum=score.momentum if score else None,
        sentiment=score.sentiment if score else None,
        risk_tier=score.risk_tier if score else None,
        pe=pe, pb=pb, roe=roe, revenue_growth=rev_g,
        profit_margin=pm, dividend_yield=dy,
    )


def _bucket_score(s):
    if s is None or not _is_finite(s):
        return None
    if s < 20:
        return 0
    if s < 40:
        return 1
    if s < 60:
        return 2
    if s < 80:
        return 3
    return 4


def _bucketize(values, *, top_n=10, order=None):
    """Count occurrences per label, return top-N as CountBucket list.

    `order` (optional): preserve a specific label order in the result
    (used for risk_tier where conservative/moderate/aggressive has
    inherent ordering). Values not in `order` get appended afterwards
    sorted by count desc.
    """
    from collections import Counter
    counts = Counter(values)
    if order is not None:
        ordered = [(lbl, counts.get(lbl, 0)) for lbl in order if counts.get(lbl, 0) > 0]
        rest = sorted(
            ((lbl, c) for lbl, c in counts.items() if lbl not in order),
            key=lambda x: -x[1],
        )
        all_pairs = ordered + rest
    else:
        all_pairs = sorted(counts.items(), key=lambda x: -x[1])
    return [CountBucket(label=lbl, count=c) for lbl, c in all_pairs[:top_n]]


def _market_cap_buckets(caps):
    """Bucket market caps into mega/large/mid/small/micro per S&P
    convention. Returns ordered CountBucket list (so the chart axis
    is monotonic from largest to smallest)."""
    thresholds = [
        ("Mega cap (>$200B)", 200_000_000_000),
        ("Large cap ($10-200B)", 10_000_000_000),
        ("Mid cap ($2-10B)", 2_000_000_000),
        ("Small cap ($300M-2B)", 300_000_000),
        ("Micro cap (<$300M)", 0),
    ]
    counts = {label: 0 for label, _ in thresholds}
    for c in caps:
        if c is None or not _is_finite(c):
            continue
        for label, lo in thresholds:
            if c >= lo:
                counts[label] += 1
                break
    return [CountBucket(label=label, count=counts[label]) for label, _ in thresholds]


def _sector_rollup(db: Session) -> list[SectorSummary]:
    """Compute the per-sector SectorSummary list — fast path, ~50-200ms.

    Two design rules keep this cheap enough to call on every hub-page
    landing without choking under a cold (or open-circuit) yfinance:

      1. Composite-score aggregates come from SQL: a single
         GROUP BY sector over the stock_scores table gives the avg
         composite in one query.
      2. Fundamentals medians (P/E, P/B, ROE, dividend yield) read
         ONLY the in-memory L1 cache (`_CACHE`). Cold tickers
         contribute nothing — they don't trigger a network call.
         L1 is hydrated from L2 at startup (~848 entries on this
         catalog), so warm-tickers coverage is typically >75%, plenty
         for a stable median.

    The slow per-stock-detail loop that this function used to do
    (`get_fundamentals(ticker)` per ticker) was responsible for the
    hub-page hang during the May 2026 audit — 1097 stocks × ~120ms
    per fundamentals call = 2+ minutes wall time, plus a long tail of
    breaker-open empties when yfinance was throttled. The L1-only
    pattern collapses that to a microsecond dict lookup per ticker.
    """
    # 1. SQL aggregate: per-sector (stock_count, avg_composite).
    # The DISTINCT on ticker defeats the legacy duplicate-row issue
    # documented in CLAUDE.md. Equity-only: ETF/ETN rows carry a sector
    # label (SPY sat in Financials) but no meaningful fundamentals — a
    # leveraged ETF's P/E in the sector median would distort the
    # benchmark real companies are compared against.
    score_rows = db.execute(
        select(
            Stock.sector,
            func.count(func.distinct(Stock.ticker)).label("stock_count"),
            func.avg(StockScore.composite).label("avg_score"),
        )
        .outerjoin(StockScore, StockScore.stock_id == Stock.id)
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
        .where(Stock.sector.is_not(None))
        .group_by(Stock.sector)
        .order_by(Stock.sector.asc())
    ).all()

    # 2. Collect tickers per sector for the L1-only fundamentals pass.
    # One SELECT for the entire universe, then bucket in Python — beats
    # N+1 queries (one per sector) on this read path. Same equity-only
    # filter as above so ETF fundamentals never enter the medians.
    ticker_rows = db.execute(
        select(Stock.sector, Stock.ticker)
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
        .where(Stock.sector.is_not(None))
    ).all()
    tickers_by_sector: dict[str, set[str]] = {}
    for sector, ticker in ticker_rows:
        if sector:
            tickers_by_sector.setdefault(sector, set()).add(ticker)

    # 3. For each sector, pull warm fundamentals from L1 only. Cold or
    # missing entries are skipped (no fetch). This is the speed win.
    cache = stock_fundamentals_service._CACHE  # noqa: SLF001
    out: list[SectorSummary] = []
    for sector_name, stock_count, avg_score in score_rows:
        if not sector_name:
            continue
        pes, pbs, roes, dys = [], [], [], []
        for ticker in tickers_by_sector.get(sector_name, ()):
            funds = cache.get(ticker)
            if funds is None or funds.micro is None:
                continue
            m = funds.micro
            if _is_finite(m.trailing_pe) and m.trailing_pe is not None and m.trailing_pe > 0:
                pes.append(float(m.trailing_pe))
            if _is_finite(m.price_to_book) and m.price_to_book is not None and m.price_to_book > 0:
                pbs.append(float(m.price_to_book))
            if _is_finite(m.return_on_equity):
                roes.append(float(m.return_on_equity) * 100.0)
            normd = _normalise_div_yield(m.dividend_yield)
            if normd is not None:
                dys.append(normd)
        out.append(SectorSummary(
            name=sector_name,
            stock_count=int(stock_count or 0),
            avg_score=float(avg_score) if avg_score is not None else None,
            median_pe=_safe_median(pes) if pes else None,
            median_pb=_safe_median(pbs) if pbs else None,
            median_roe=_safe_median(roes) if roes else None,
            median_dividend_yield=_safe_median(dys) if dys else None,
        ))
    return out


def _technical_rollup(db: Session) -> dict[str, tuple[int, float]]:
    """Per-sector Tecnico aggregate: sector → (n, avg technical composite).

    One SQL GROUP BY over `technical_scores` INNER-joined to equity-only
    visible stocks — INNER because a stock without a technical score has
    nothing to contribute (unlike the Qualità rollup's outerjoin, where
    the stock count itself matters). Cheap enough (~1000 rows) to run on
    every overview recompute inside the 60s TTL cache.
    """
    rows = db.execute(
        select(
            Stock.sector,
            func.count(func.distinct(Stock.ticker)),
            func.avg(TechnicalScore.composite),
        )
        .join(TechnicalScore, TechnicalScore.stock_id == Stock.id)
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
        .where(Stock.sector.is_not(None))
        .group_by(Stock.sector)
    ).all()
    return {
        sector: (int(n or 0), float(avg))
        for sector, n, avg in rows
        if sector and avg is not None
    }


def _sector_daily_changes(db: Session) -> dict[str, float]:
    """Sector → Δ% giornaliero, read from the latest market snapshot.

    The dashboard's sector heatmap shows `payload["sectors"]` computed by
    `market_stats_service.aggregate_by_sector` at scan time. Re-deriving
    the same number here would mean re-loading OHLCV for the whole
    universe — instead we read the persisted block (snapshot-derived by
    design; a missing/legacy snapshot degrades to an empty map and the
    tiles simply show no Δ%).
    """
    snap = db.get(MarketSnapshot, 1)
    if snap is None:
        return {}
    try:
        payload = json.loads(snap.payload)
    except (TypeError, ValueError):
        return {}
    out: dict[str, float] = {}
    for row in payload.get("sectors") or []:
        name = row.get("sector")
        chg = row.get("avg_change_pct")
        if name and isinstance(chg, (int, float)) and _is_finite(chg):
            out[name] = float(chg)
    return out


def _score_trends(db: Session, *, n_captures: int = 30) -> dict[str, list[SectorTrendPoint]]:
    """Sector → Qualità composite trend over the last ~30 capture days.

    One GROUP BY (sector, captured_on) over `score_history` (qualita lens
    only — the Tecnico series belongs to a different lens and mixing them
    would average apples with oranges). The capture-day window comes from
    a DISTINCT-dates subquery instead of a wall-clock cutoff so gaps
    (weekends, skipped scans) don't shrink the sparkline.
    """
    recent_days = (
        select(ScoreHistory.captured_on)
        .where(ScoreHistory.lens == "qualita")
        .distinct()
        .order_by(ScoreHistory.captured_on.desc())
        .limit(n_captures)
    )
    rows = db.execute(
        select(
            Stock.sector,
            ScoreHistory.captured_on,
            func.avg(ScoreHistory.composite),
        )
        .join(Stock, Stock.id == ScoreHistory.stock_id)
        .where(ScoreHistory.lens == "qualita")
        .where(ScoreHistory.captured_on.in_(recent_days))
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
        .where(Stock.sector.is_not(None))
        .group_by(Stock.sector, ScoreHistory.captured_on)
        .order_by(ScoreHistory.captured_on.asc())
    ).all()
    out: dict[str, list[SectorTrendPoint]] = {}
    for sector, captured_on, avg in rows:
        if not sector or avg is None:
            continue
        out.setdefault(sector, []).append(
            SectorTrendPoint(date=captured_on.isoformat(), avg=float(avg))
        )
    return out


def _signals_7d(db: Session, *, today: date | None = None) -> dict[str, dict[str, int]]:
    """Sector → {"total", "bull", "bear"} signal counts over the last 7 days.

    Window keyed on `signal_date` (the bar where the condition matched,
    not the wall-clock detection) so a backfilled Monday scan doesn't
    inflate "this week". Archived alerts excluded — the tile chip links
    to /alerts whose default view is non-archived, and the two numbers
    must agree. Tone split via json_extract on the snapshot (same idiom
    as alert_service); tones other than bull/bear count in the total only.
    """
    cutoff = (today or date.today()) - timedelta(days=7)
    tone_col = func.json_extract(Alert.snapshot, "$.tone")
    rows = db.execute(
        select(Stock.sector, tone_col, func.count(Alert.id))
        .join(Stock, Stock.id == Alert.stock_id)
        .where(Alert.signal_date >= cutoff)
        .where(Alert.archived_at.is_(None))
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
        .where(Stock.sector.is_not(None))
        .group_by(Stock.sector, tone_col)
    ).all()
    out: dict[str, dict[str, int]] = {}
    for sector, tone, count in rows:
        if not sector:
            continue
        entry = out.setdefault(sector, {"total": 0, "bull": 0, "bear": 0})
        entry["total"] += int(count or 0)
        if tone in ("bull", "bear"):
            entry[tone] += int(count or 0)
    return out


def _etf_proxies(db: Session) -> dict[str, str]:
    """Sector → SPDR proxy ticker, ONLY for tickers present in the catalog.

    The static map is a candidate list, not a truth claim — one IN query
    against `stocks` decides which proxies are actually navigable via
    /stocks/{ticker}. No instrument_type filter here: the proxies ARE
    ETFs and the link goes to the stock detail page, not into any
    equity-only aggregate.
    """
    candidates = set(SECTOR_ETF_PROXY.values())
    present = {
        t for (t,) in db.execute(
            select(Stock.ticker).where(Stock.ticker.in_(candidates))
        ).all()
    }
    return {
        sector: ticker
        for sector, ticker in SECTOR_ETF_PROXY.items()
        if ticker in present
    }


def _industry_rollup(db: Session) -> list[IndustryRow]:
    """Per-industry stock count + avg composite via a single SQL aggregate.

    Cheap path: SQL GROUP BY over stock_scores joined to stocks, plus a
    second pass to map each industry to its parent sector (so the FE can
    group industries under their sector heading without a second query).
    No yfinance hits — keeps the overview endpoint fast even when the
    fundamentals cache is cold.
    """
    # Stocks per (industry, sector) — one row per unique ticker via DISTINCT
    # to defeat the legacy duplicate-row issue documented in CLAUDE.md.
    # Equity-only for the same reason as `_sector_rollup`: ETFs are not
    # peers of the companies in an industry bucket.
    rows = db.execute(
        select(
            Stock.industry,
            Stock.sector,
            func.count(func.distinct(Stock.ticker)),
            func.avg(StockScore.composite),
        )
        .outerjoin(StockScore, StockScore.stock_id == Stock.id)
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
        .where(Stock.industry.is_not(None))
        .group_by(Stock.industry, Stock.sector)
    ).all()

    # An industry can appear under multiple sectors (rare but possible for
    # cross-sector buckets like "Other"). We collapse by industry, picking
    # the SECTOR that holds the most stocks for that industry as the
    # "primary" sector for display.
    by_industry: dict[str, dict] = {}
    for industry, sector, cnt, avg_score in rows:
        if not industry:
            continue
        entry = by_industry.setdefault(industry, {
            "stock_count": 0,
            "score_weighted_sum": 0.0,
            "score_weight": 0.0,
            "sector_counts": {},
        })
        entry["stock_count"] += int(cnt or 0)
        if avg_score is not None:
            entry["score_weighted_sum"] += float(avg_score) * int(cnt or 0)
            entry["score_weight"] += int(cnt or 0)
        entry["sector_counts"][sector] = entry["sector_counts"].get(sector, 0) + int(cnt or 0)

    out: list[IndustryRow] = []
    for name, agg in by_industry.items():
        # Pick the dominant parent sector for this industry — the one
        # with the most stocks. Ties broken alphabetically for stability.
        sector_counts = agg["sector_counts"]
        primary_sector = (
            sorted(sector_counts.items(), key=lambda kv: (-kv[1], kv[0] or ""))[0][0]
            if sector_counts else None
        )
        avg = (
            agg["score_weighted_sum"] / agg["score_weight"]
            if agg["score_weight"] > 0 else None
        )
        out.append(IndustryRow(
            name=name,
            sector=primary_sector,
            stock_count=agg["stock_count"],
            avg_score=avg,
        ))
    # Sort by sector ASC, then stock_count DESC inside sector — gives the
    # FE a natural rendering order for "group by sector + sort by size".
    out.sort(key=lambda r: (r.sector or "~", -r.stock_count))
    return out


@router.get("", response_model=list[SectorSummary])
def list_sectors(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return _sector_rollup(db)


@router.get("/overview", response_model=SectorsOverviewOut)
def sectors_overview(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """One-shot payload for the /sectors hub page.

    Combines:
      - Top-level counts (total stocks / sectors / industries).
      - Per-sector rollups (reuses `_sector_rollup` — SQL aggregates +
        L1-only fundamentals, no network).
      - Per-industry table (single SQL GROUP BY via `_industry_rollup`).

    Memoized in `services.sectors_overview_cache` with a 60s TTL so the
    hub-page burst pattern (multiple tabs, F5, in-and-out navigation)
    doesn't replay the SQL aggregates on every hit. The cache lives in
    the services layer so `recompute_all` can invalidate it at the end
    of every recompute without importing this router (see the cache
    module's docstring for the layering rationale).
    """
    cached = sectors_overview_cache.get_cached()
    if cached is not None:
        return cached

    sectors = _sector_rollup(db)
    industries = _industry_rollup(db)

    # ESP-2 enrichments — each one is a single query (or a JSON read for
    # the snapshot Δ%), all memoized together with the payload below so
    # the 60s cache keeps the hub-page burst pattern to one SQL pass.
    tech = _technical_rollup(db)
    changes = _sector_daily_changes(db)
    trends = _score_trends(db)
    signals = _signals_7d(db)
    proxies = _etf_proxies(db)
    sectors = [
        s.model_copy(update={
            "avg_technical": tech[s.name][1] if s.name in tech else None,
            "technical_count": tech[s.name][0] if s.name in tech else 0,
            "change_pct": changes.get(s.name),
            "signals_7d": signals.get(s.name, {}).get("total", 0),
            "signals_7d_bull": signals.get(s.name, {}).get("bull", 0),
            "signals_7d_bear": signals.get(s.name, {}).get("bear", 0),
            "etf_proxy": proxies.get(s.name),
            "score_trend": trends.get(s.name, []),
        })
        for s in sectors
    ]
    # Equity-only, mirroring the per-sector cards: without the filter
    # the ETF rows inflate the "Stock totali" tile relative to the sum
    # of the sector cards and the gap reads as missing data.
    total_stocks = db.execute(
        select(func.count(func.distinct(Stock.ticker)))
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
    ).scalar() or 0
    payload = SectorsOverviewOut(
        total_stocks=int(total_stocks),
        total_sectors=len(sectors),
        total_industries=len(industries),
        sectors=sectors,
        industries=industries,
    )
    sectors_overview_cache.store(payload)
    return payload


@router.get("/{name}/detail", response_model=SectorDetailOut)
def get_sector_detail(
    name: Annotated[str, Path(min_length=1, max_length=128)],
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    # Equity-only: an ETF with a sector label (SPY in Financials) must
    # not surface among the sector's peer stocks nor contribute to the
    # KPI medians below.
    stocks = db.execute(
        select(Stock)
        .where(visible_country_clause())
        .where(Stock.instrument_type == "equity")
        .where(Stock.sector == name)
        .order_by(Stock.ticker.asc())
    ).scalars().all()

    seen = set()
    unique_stocks = []
    for st in stocks:
        if st.ticker in seen:
            continue
        seen.add(st.ticker)
        unique_stocks.append(st)

    if not unique_stocks:
        raise HTTPException(status_code=404, detail="Sector not found")

    # Bulk-load all scores in ONE SELECT instead of one query per stock
    # (the old loop issued ~150 SELECTs for Information Technology).
    # `.scalars().all()` + dict keeps last-row-wins semantics — stock_id
    # is effectively unique in stock_scores so collisions don't occur.
    score_by_stock_id = {
        sc.stock_id: sc
        for sc in db.execute(
            select(StockScore).where(
                StockScore.stock_id.in_([st.id for st in unique_stocks])
            )
        ).scalars().all()
    }

    rows = []
    composites = []
    market_caps = []
    rev_gs, pms = [], []
    buckets = [0, 0, 0, 0, 0]

    for st in unique_stocks:
        score = score_by_stock_id.get(st.id)
        row = _build_stock_row(st, score)
        rows.append(row)
        if row.composite is not None:
            composites.append(row.composite)
            b = _bucket_score(row.composite)
            if b is not None:
                buckets[b] += 1
        if row.market_cap is not None:
            market_caps.append(row.market_cap)
        if row.revenue_growth is not None:
            rev_gs.append(row.revenue_growth)
        if row.profit_margin is not None:
            pms.append(row.profit_margin)

    pes = [r.pe for r in rows if r.pe is not None]
    pbs = [r.pb for r in rows if r.pb is not None]
    roes = [r.roe for r in rows if r.roe is not None]
    dys = [r.dividend_yield for r in rows if r.dividend_yield is not None]

    # Tecnico lens KPI: one aggregate over the sector's stock ids. Kept
    # separate from the StockScore bulk-load above — different table,
    # and the avg must only span stocks that HAVE a technical score.
    tech_count, tech_avg = db.execute(
        select(
            func.count(TechnicalScore.stock_id),
            func.avg(TechnicalScore.composite),
        ).where(TechnicalScore.stock_id.in_([st.id for st in unique_stocks]))
    ).one()

    # V3.2 enrichments: distributions across industry / country / risk
    # / market_cap, plus per-pillar averages. All computed in-loop on
    # the already-built `rows` list — no additional fetches.
    pillar_avgs = PillarAverages(
        profitability=_safe_mean([r.profitability for r in rows if r.profitability is not None]),
        sustainability=_safe_mean([r.sustainability for r in rows if r.sustainability is not None]),
        growth=_safe_mean([r.growth for r in rows if r.growth is not None]),
        value=_safe_mean([r.value for r in rows if r.value is not None]),
        momentum=_safe_mean([r.momentum for r in rows if r.momentum is not None]),
        sentiment=_safe_mean([r.sentiment for r in rows if r.sentiment is not None]),
    )
    industry_breakdown = _bucketize([r.industry or "(no industry)" for r in rows], top_n=12)
    country_distribution = _bucketize([r.country or "(no country)" for r in rows], top_n=15)
    risk_distribution = _bucketize(
        [r.risk_tier or "(unknown)" for r in rows],
        top_n=4,
        order=["conservative", "moderate", "aggressive"],
    )
    market_cap_distribution = _market_cap_buckets([r.market_cap for r in rows])

    kpis = SectorKpis(
        stock_count=len(rows),
        avg_composite=_safe_mean(composites) if composites else None,
        median_composite=_safe_median(composites) if composites else None,
        avg_technical=float(tech_avg) if tech_avg is not None else None,
        technical_count=int(tech_count or 0),
        median_pe=_safe_median(pes) if pes else None,
        median_pb=_safe_median(pbs) if pbs else None,
        median_roe=_safe_median(roes) if roes else None,
        median_revenue_growth=_safe_median(rev_gs) if rev_gs else None,
        median_profit_margin=_safe_median(pms) if pms else None,
        median_dividend_yield=_safe_median(dys) if dys else None,
        median_market_cap=_safe_median(market_caps) if market_caps else None,
        score_distribution=buckets,
        pillar_averages=pillar_avgs,
        industry_breakdown=industry_breakdown,
        country_distribution=country_distribution,
        risk_distribution=risk_distribution,
        market_cap_distribution=market_cap_distribution,
    )

    scored = [r for r in rows if r.composite is not None]
    scored_desc = sorted(scored, key=lambda r: r.composite or 0.0, reverse=True)
    top_picks = scored_desc[:5]
    bottom_picks = list(reversed(scored_desc[-5:])) if len(scored_desc) > 5 else []

    return SectorDetailOut(
        sector=name,
        kpis=kpis,
        top_picks=top_picks,
        bottom_picks=bottom_picks,
        stocks=rows,
    )
