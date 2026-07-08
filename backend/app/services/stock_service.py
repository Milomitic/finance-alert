"""Stock search and filter options."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, distinct, exists, func, nullslast, or_, select
from sqlalchemy.orm import Session

from app.core.visibility import visible_country_clause
from app.models import (
    Alert,
    Index,
    Stock,
    StockIndex,
    StockMetrics,
    StockScore,
    TechnicalScore,
)

# Allowed sort columns; whitelist guards against SQL injection / typos.
# Columns from JOINed tables (`composite`, `risk_tier`) are sortable too —
# the search query LEFT JOINs stock_scores / technical_scores / stock_metrics
# so screener users can rank by score, technical posture, or EOD price metrics
# (price/change%/RSI/volume) directly server-side.
SORTABLE_COLUMNS: dict[str, object] = {
    "ticker": Stock.ticker,
    "name": Stock.name,
    "market_cap": Stock.market_cap,
    "sector": Stock.sector,
    "industry": Stock.industry,
    "exchange": Stock.exchange,
    "composite": StockScore.composite,
    "profitability": StockScore.profitability,
    "sustainability": StockScore.sustainability,
    "growth": StockScore.growth,
    "value": StockScore.value,
    # NOTE: no "momentum" here — the fundamental Momentum pillar was removed
    # (StockScore.momentum is always NULL; price-action momentum lives on the
    # Tecnico lens as "tech_momentum"). Sorting by an always-NULL column was
    # dead API surface.
    "sentiment": StockScore.sentiment,
    "tech_composite": TechnicalScore.composite,
    "tech_trend": TechnicalScore.trend,
    "tech_momentum": TechnicalScore.momentum,
    "tech_structure": TechnicalScore.structure,
    "tech_volume": TechnicalScore.volume,
    "tech_rel_strength": TechnicalScore.rel_strength,
    # EOD price/volume metrics (from stock_metrics). `change_pct` is now a real
    # server-side column, retiring the old client-only re-sort hack.
    "price": StockMetrics.last_close,
    "change_pct": StockMetrics.change_pct,
    "rsi14": StockMetrics.rsi14,
    "vol_ratio": StockMetrics.vol_ratio,
    "vol_today": StockMetrics.vol_today,
}


@dataclass
class StockFilter:
    q: str | None = None
    exchanges: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    index_codes: list[str] = field(default_factory=list)
    # Risk tiers from the score table. Empty list = don't filter on risk.
    risk_tiers: list[str] = field(default_factory=list)
    # Minimum composite score (0-100). None = no threshold. Stocks without a
    # computed score are excluded when this is set (LEFT JOIN nullability).
    min_score: float | None = None
    # Maximum composite score (0-100). Stocks above this cap are excluded.
    score_max: float | None = None
    # Per-pillar minimum thresholds (0-100). Stocks without a score row (or
    # with a NULL pillar) are excluded when any of these are set.
    profitability_min: float | None = None
    sustainability_min: float | None = None
    growth_min: float | None = None
    value_min: float | None = None
    sentiment_min: float | None = None
    # Technical score (continuous) filters.
    tech_min: float | None = None
    tech_max: float | None = None
    postures: list[str] = field(default_factory=list)
    # EOD price/volume metric filters (from stock_metrics; require a metrics row,
    # i.e. a stock with a close + enough bars for the given indicator).
    price_min: float | None = None
    price_max: float | None = None
    change_min: float | None = None   # daily % change lower bound
    change_max: float | None = None
    rsi_min: float | None = None
    rsi_max: float | None = None
    above_ema50: bool = False         # last_close > ema50
    above_ema200: bool = False
    near_52w_high: bool = False       # last_close >= 0.95 * high_252
    near_52w_low: bool = False        # last_close <= 1.05 * low_252
    vol_spike: bool = False           # vol_ratio > 2.0
    volume_min: float | None = None   # today's share volume lower bound
    market_cap_min: float | None = None
    market_cap_max: float | None = None
    has_signals: bool = False         # has >=1 active (non-archived) RECENT alert
    # Recency window for has_signals, in calendar days (validated 1..90 at the
    # API; clamped defensively here too). The unbounded EXISTS used to match
    # ~99% of the universe — useless as a screen.
    signals_within_days: int = 7
    exclude_etf: bool = False         # drop instrument_type='etf' rows
    sort_by: str = "ticker"
    sort_dir: str = "asc"
    limit: int = 50
    offset: int = 0


@dataclass
class StockScoreRef:
    """Minimal score fields surfaced on the screener row. Optional — None
    when the stock hasn't been scored yet."""
    composite: float | None = None
    risk_tier: str | None = None
    profitability: float | None = None
    sustainability: float | None = None
    growth: float | None = None
    value: float | None = None
    # No momentum field: the fundamental Momentum pillar was removed from the
    # composite (see CLAUDE.md) — the column is always NULL, so surfacing it
    # on the screener row was dead payload.
    sentiment: float | None = None


@dataclass
class StockTechRef:
    """Continuous technical score fields surfaced on the screener row.
    All None when the stock has no technical score yet."""
    composite: float | None = None
    trend: float | None = None
    momentum: float | None = None
    structure: float | None = None
    volume: float | None = None
    rel_strength: float | None = None
    signals: float | None = None
    posture: str | None = None


@dataclass
class StockMetricsRef:
    """EOD price/volume metrics surfaced on the screener row (from stock_metrics).
    All None when the stock has no metrics row yet (no close / too few bars)."""
    last_close: float | None = None
    change_pct: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    high_252: float | None = None
    low_252: float | None = None
    vol_ratio: float | None = None
    # Raw volume pair behind vol_ratio — today's share count + the 20-bar
    # average. Filterable via volume_min since Phase A; surfaced so the
    # screener can render/sort an absolute Volume column too.
    vol_today: float | None = None
    vol_avg_20: float | None = None


@dataclass
class StockSearchItem:
    """Stock + optional fundamental + technical score + EOD metrics for the screener."""
    stock: Stock
    score: StockScoreRef
    technical: StockTechRef = field(default_factory=StockTechRef)
    metrics: StockMetricsRef = field(default_factory=StockMetricsRef)


@dataclass
class StockPage:
    items: list[StockSearchItem]
    total: int
    has_more: bool
    # As-of timestamp of the stock_metrics refresh (all rows share one
    # computed_at per scan; we surface MAX as the single meta value). None
    # when the table is empty (no scan has persisted metrics yet).
    metrics_computed_at: datetime | None = None


@dataclass
class IndexOption:
    code: str
    name: str


@dataclass
class FilterOptions:
    exchanges: list[str]
    sectors: list[str]
    industries: list[str]
    countries: list[str]
    indices: list[IndexOption]


def _apply_filter(stmt, f: StockFilter):
    # Hide catalog-only countries (CN/JP/KR) from every user-facing
    # query. They live in the catalog only to feed dashboard breadth
    # + Asia market-mood; the screener, search, watchlist-add, and
    # alert generation all need to skip them. See
    # `app/core/visibility.py` for the single source of truth.
    stmt = stmt.where(visible_country_clause())
    if f.q:
        like = f"{f.q.lower()}%"
        sub = f"%{f.q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Stock.ticker).like(like), func.lower(Stock.name).like(sub))
        )
    if f.exchanges:
        stmt = stmt.where(Stock.exchange.in_(f.exchanges))
    if f.sectors:
        stmt = stmt.where(Stock.sector.in_(f.sectors))
    if f.industries:
        stmt = stmt.where(Stock.industry.in_(f.industries))
    if f.countries:
        stmt = stmt.where(Stock.country.in_(f.countries))
    if f.index_codes:
        stmt = (
            stmt.join(StockIndex, StockIndex.stock_id == Stock.id)
            .join(Index, Index.id == StockIndex.index_id)
            .where(Index.code.in_(f.index_codes))
            .distinct()
        )
    # Risk-tier and min-score require StockScore JOIN. Both filters drop
    # stocks without a computed score — that's the explicit semantics
    # ("show me only scored stocks above 70" excludes unscored rows).
    if f.risk_tiers:
        stmt = stmt.where(StockScore.risk_tier.in_(f.risk_tiers))
    if f.min_score is not None:
        stmt = stmt.where(StockScore.composite >= f.min_score)
    if f.score_max is not None:
        stmt = stmt.where(StockScore.composite <= f.score_max)
    if f.profitability_min is not None:
        stmt = stmt.where(StockScore.profitability >= f.profitability_min)
    if f.sustainability_min is not None:
        stmt = stmt.where(StockScore.sustainability >= f.sustainability_min)
    if f.growth_min is not None:
        stmt = stmt.where(StockScore.growth >= f.growth_min)
    if f.value_min is not None:
        stmt = stmt.where(StockScore.value >= f.value_min)
    if f.sentiment_min is not None:
        stmt = stmt.where(StockScore.sentiment >= f.sentiment_min)
    if f.tech_min is not None:
        stmt = stmt.where(TechnicalScore.composite >= f.tech_min)
    if f.tech_max is not None:
        stmt = stmt.where(TechnicalScore.composite <= f.tech_max)
    if f.postures:
        stmt = stmt.where(TechnicalScore.posture.in_(f.postures))
    # EOD price/volume metric filters (stock_metrics). A predicate that
    # references a NULL metric (e.g. above_ema200 when ema200 is NULL) excludes
    # the row — correct, since we can't confirm the condition without the value.
    if f.price_min is not None:
        stmt = stmt.where(StockMetrics.last_close >= f.price_min)
    if f.price_max is not None:
        stmt = stmt.where(StockMetrics.last_close <= f.price_max)
    if f.change_min is not None:
        stmt = stmt.where(StockMetrics.change_pct >= f.change_min)
    if f.change_max is not None:
        stmt = stmt.where(StockMetrics.change_pct <= f.change_max)
    if f.rsi_min is not None:
        stmt = stmt.where(StockMetrics.rsi14 >= f.rsi_min)
    if f.rsi_max is not None:
        stmt = stmt.where(StockMetrics.rsi14 <= f.rsi_max)
    if f.above_ema50:
        stmt = stmt.where(StockMetrics.last_close > StockMetrics.ema50)
    if f.above_ema200:
        stmt = stmt.where(StockMetrics.last_close > StockMetrics.ema200)
    if f.near_52w_high:
        stmt = stmt.where(StockMetrics.last_close >= 0.95 * StockMetrics.high_252)
    if f.near_52w_low:
        stmt = stmt.where(StockMetrics.last_close <= 1.05 * StockMetrics.low_252)
    if f.vol_spike:
        stmt = stmt.where(StockMetrics.vol_ratio > 2.0)
    if f.volume_min is not None:
        stmt = stmt.where(StockMetrics.vol_today >= f.volume_min)
    if f.market_cap_min is not None:
        stmt = stmt.where(Stock.market_cap >= f.market_cap_min)
    if f.market_cap_max is not None:
        stmt = stmt.where(Stock.market_cap <= f.market_cap_max)
    if f.has_signals:
        # Recency-bound EXISTS: without a time bound this matched 929/938
        # stocks (any alert EVER fired kept the stock flagged), making the
        # toggle useless as a screen. Bound on `signal_date` — the bar date
        # the condition matched — falling back to the `triggered_at` date for
        # legacy rows that predate the column (dual-timestamp model).
        days = max(1, min(int(f.signals_within_days or 7), 90))
        cutoff = date.today() - timedelta(days=days)
        stmt = stmt.where(
            exists().where(
                and_(
                    Alert.stock_id == Stock.id,
                    Alert.archived_at.is_(None),
                    func.coalesce(
                        Alert.signal_date, func.date(Alert.triggered_at)
                    ) >= cutoff,
                )
            )
        )
    if f.exclude_etf:
        # ETFs are equities in every other respect (they have metrics +
        # technical scores) — this is a plain instrument_type predicate.
        stmt = stmt.where(Stock.instrument_type != "etf")
    return stmt


def _apply_sort(stmt, f: StockFilter):
    """Apply ORDER BY using the whitelist, with `ticker ASC` as a stable tiebreaker.

    The tiebreaker matters when sorting by a nullable / non-unique column
    (sector, market_cap): without it pagination would walk a non-deterministic
    order and rows could appear/skip across pages.
    """
    col = SORTABLE_COLUMNS.get(f.sort_by, Stock.ticker)
    direction = (f.sort_dir or "asc").lower()
    if direction not in ("asc", "desc"):
        direction = "asc"
    # NULLS LAST on both directions. SQLite treats NULL as smaller than
    # everything, so a plain ASC sort put every unscored/metricless row on
    # page 1 of the screener. SQLite has supported the standard `NULLS LAST`
    # clause since 3.30 (2019) — the old comment claiming otherwise was wrong.
    # DESC already ends with NULLs by default, but we make it explicit so the
    # ordering contract is direction-independent.
    primary = nullslast(col.desc()) if direction == "desc" else nullslast(col.asc())
    if f.sort_by == "ticker":
        return stmt.order_by(primary)
    return stmt.order_by(primary, Stock.ticker.asc())


def search_stocks(db: Session, f: StockFilter) -> StockPage:
    """LEFT JOIN stock_scores so the screener can show + filter + sort by
    composite score. The JOIN is left-outer so unscored stocks still appear
    (with score=None), unless the user explicitly filters by risk_tiers /
    min_score, which require a non-null score by definition.
    """
    limit = max(1, min(f.limit, 500))
    # SELECT Stock + all score columns needed for the screener row
    base = select(
        Stock,
        StockScore.composite,
        StockScore.risk_tier,
        StockScore.profitability,
        StockScore.sustainability,
        StockScore.growth,
        StockScore.value,
        StockScore.sentiment,
        TechnicalScore.composite.label("tech_composite"),
        TechnicalScore.trend.label("tech_trend"),
        TechnicalScore.momentum.label("tech_momentum"),
        TechnicalScore.structure.label("tech_structure"),
        TechnicalScore.volume.label("tech_volume"),
        TechnicalScore.rel_strength.label("tech_rel_strength"),
        TechnicalScore.signals.label("tech_signals"),
        TechnicalScore.posture.label("tech_posture"),
        StockMetrics.last_close.label("m_last_close"),
        StockMetrics.change_pct.label("m_change_pct"),
        StockMetrics.ema50.label("m_ema50"),
        StockMetrics.ema200.label("m_ema200"),
        StockMetrics.rsi14.label("m_rsi14"),
        StockMetrics.high_252.label("m_high_252"),
        StockMetrics.low_252.label("m_low_252"),
        StockMetrics.vol_ratio.label("m_vol_ratio"),
        StockMetrics.vol_today.label("m_vol_today"),
        StockMetrics.vol_avg_20.label("m_vol_avg_20"),
    ).outerjoin(StockScore, StockScore.stock_id == Stock.id).outerjoin(
        TechnicalScore, TechnicalScore.stock_id == Stock.id
    ).outerjoin(StockMetrics, StockMetrics.stock_id == Stock.id)
    base = _apply_filter(base, f)

    # COUNT must be over the same FROM clause (with the JOIN + filters
    # applied) so the total reflects exactly what would be paged through.
    count_stmt = select(func.count()).select_from(base.subquery())
    total = db.execute(count_stmt).scalar_one()

    sorted_stmt = _apply_sort(base, f)
    rows = db.execute(sorted_stmt.limit(limit + 1).offset(f.offset)).all()
    has_more = len(rows) > limit
    items = [
        StockSearchItem(
            stock=row[0],
            score=StockScoreRef(
                composite=row[1],
                risk_tier=row[2],
                profitability=row[3],
                sustainability=row[4],
                growth=row[5],
                value=row[6],
                sentiment=row[7],
            ),
            technical=StockTechRef(
                composite=row[8],
                trend=row[9],
                momentum=row[10],
                structure=row[11],
                volume=row[12],
                rel_strength=row[13],
                signals=row[14],
                posture=row[15],
            ),
            metrics=StockMetricsRef(
                last_close=row[16],
                change_pct=row[17],
                ema50=row[18],
                ema200=row[19],
                rsi14=row[20],
                high_252=row[21],
                low_252=row[22],
                vol_ratio=row[23],
                vol_today=row[24],
                vol_avg_20=row[25],
            ),
        )
        for row in rows[:limit]
    ]
    # Metrics as-of: every stock_metrics row of a refresh shares one
    # computed_at, so MAX over the table IS the last refresh time. One
    # aggregate query (~ms) — lets the screener render "metriche al HH:MM"
    # and flag a stale scan.
    metrics_computed_at = db.execute(
        select(func.max(StockMetrics.computed_at))
    ).scalar()
    return StockPage(
        items=items, total=int(total), has_more=has_more,
        metrics_computed_at=metrics_computed_at,
    )


def get_filter_options(db: Session) -> FilterOptions:
    exchanges = [
        r[0]
        for r in db.execute(select(distinct(Stock.exchange)).order_by(Stock.exchange)).all()
        if r[0]
    ]
    sectors = [
        r[0]
        for r in db.execute(select(distinct(Stock.sector)).order_by(Stock.sector)).all()
        if r[0]
    ]
    industries = [
        r[0]
        for r in db.execute(select(distinct(Stock.industry)).order_by(Stock.industry)).all()
        if r[0]
    ]
    countries = [
        r[0]
        for r in db.execute(select(distinct(Stock.country)).order_by(Stock.country)).all()
        if r[0]
    ]
    indices = [
        IndexOption(code=row.code, name=row.name)
        for row in db.execute(select(Index).order_by(Index.code)).scalars().all()
    ]
    return FilterOptions(
        exchanges=exchanges,
        sectors=sectors,
        industries=industries,
        countries=countries,
        indices=indices,
    )
