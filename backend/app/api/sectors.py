"""Sector recap endpoints - /api/sectors and /api/sectors/{name}/detail.

Powers the SectorDetailPage UI: when a user clicks a sector tile in
the dashboard heatmap (or the sector badge on a stock card), they
land on a page showing peer stocks + aggregate stats for that
sector. Mirrors the role indices play via /stocks?index=CODE.
"""
from __future__ import annotations

import math
import statistics
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.visibility import visible_country_clause
from app.models import Stock, StockScore, User
from app.services import stock_fundamentals_service


router = APIRouter(prefix="/api/sectors", tags=["sectors"])


class SectorSummary(BaseModel):
    name: str
    stock_count: int
    avg_score: float | None
    median_pe: float | None
    median_pb: float | None
    median_roe: float | None
    median_dividend_yield: float | None


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
    pe = pb = roe = rev_g = pm = dy = None
    try:
        funds = stock_fundamentals_service.get_fundamentals(stock.ticker)
    except Exception:
        funds = None
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


@router.get("", response_model=list[SectorSummary])
def list_sectors(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    rows = db.execute(
        select(Stock.sector, func.count(func.distinct(Stock.ticker)))
        .where(visible_country_clause())
        .where(Stock.sector.is_not(None))
        .group_by(Stock.sector)
        .order_by(Stock.sector.asc())
    ).all()

    out = []
    for sector_name, _count in rows:
        if not sector_name:
            continue
        stocks = db.execute(
            select(Stock)
            .where(visible_country_clause())
            .where(Stock.sector == sector_name)
        ).scalars().all()
        seen = set()
        unique_stocks = []
        for st in stocks:
            if st.ticker in seen:
                continue
            seen.add(st.ticker)
            unique_stocks.append(st)

        composites = []
        pes, pbs, roes, dys = [], [], [], []
        for st in unique_stocks:
            score = db.execute(
                select(StockScore).where(StockScore.stock_id == st.id)
            ).scalar_one_or_none()
            if score is not None:
                composites.append(score.composite)
            try:
                funds = stock_fundamentals_service.get_fundamentals(st.ticker)
            except Exception:
                funds = None
            if funds is not None and funds.micro is not None:
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
            stock_count=len(unique_stocks),
            avg_score=_safe_mean(composites),
            median_pe=_safe_median(pes) if pes else None,
            median_pb=_safe_median(pbs) if pbs else None,
            median_roe=_safe_median(roes) if roes else None,
            median_dividend_yield=_safe_median(dys) if dys else None,
        ))
    return out


@router.get("/{name}/detail", response_model=SectorDetailOut)
def get_sector_detail(
    name: Annotated[str, Path(min_length=1, max_length=128)],
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stocks = db.execute(
        select(Stock)
        .where(visible_country_clause())
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

    rows = []
    composites = []
    market_caps = []
    rev_gs, pms = [], []
    buckets = [0, 0, 0, 0, 0]

    for st in unique_stocks:
        score = db.execute(
            select(StockScore).where(StockScore.stock_id == st.id)
        ).scalar_one_or_none()
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
