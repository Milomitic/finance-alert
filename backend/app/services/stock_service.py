"""Stock search and filter options."""
from dataclasses import dataclass, field

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex, StockScore

# Allowed sort columns; whitelist guards against SQL injection / typos.
# Columns from JOINed tables (`composite`, `risk_tier`) are sortable too —
# the search query LEFT JOINs stock_scores so screener users can rank by
# composite directly. `change_pct` stays client-only (no Stock-side column).
SORTABLE_COLUMNS: dict[str, object] = {
    "ticker": Stock.ticker,
    "name": Stock.name,
    "market_cap": Stock.market_cap,
    "sector": Stock.sector,
    "industry": Stock.industry,
    "exchange": Stock.exchange,
    "composite": StockScore.composite,
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
    # Minimum composite score (0–100). None = no threshold. Stocks without a
    # computed score are excluded when this is set (LEFT JOIN nullability).
    min_score: float | None = None
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


@dataclass
class StockSearchItem:
    """Stock + optional score data joined for the screener."""
    stock: Stock
    score: StockScoreRef


@dataclass
class StockPage:
    items: list[StockSearchItem]
    total: int
    has_more: bool


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
    # Hide Chinese-mainland stocks from every user-facing query (screener,
    # autocomplete, watchlist add). They're seeded into the catalog so
    # they contribute to the dashboard breadth row + Asia market-mood
    # aggregation in `market_stats_service._load_metrics`, but the user
    # explicitly opted out of trading / tracking them individually.
    # `_load_metrics` does NOT use `_apply_filter`, so the stats
    # pipeline still sees them. Single point of truth for the cutoff.
    # NULL-tolerant — test fixtures and legacy rows leave `country`
    # unset; SQL `!=` is false for NULL so we explicitly allow nulls.
    stmt = stmt.where(or_(Stock.country.is_(None), Stock.country != "CN"))
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
    # NULLS-LAST behaviour is a nice-to-have; SQLite doesn't support
    # `NULLS LAST` as a direct clause but its default for ASC is NULLS FIRST,
    # for DESC NULLS LAST. We emulate consistent ordering by chaining:
    primary = col.desc() if direction == "desc" else col.asc()
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
    # SELECT Stock, StockScore.composite, StockScore.risk_tier
    base = select(Stock, StockScore.composite, StockScore.risk_tier).outerjoin(
        StockScore, StockScore.stock_id == Stock.id
    )
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
            score=StockScoreRef(composite=row[1], risk_tier=row[2]),
        )
        for row in rows[:limit]
    ]
    return StockPage(items=items, total=int(total), has_more=has_more)


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
