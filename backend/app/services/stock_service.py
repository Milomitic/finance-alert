"""Stock search and filter options."""
from dataclasses import dataclass, field

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex


@dataclass
class StockFilter:
    q: str | None = None
    exchanges: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    index_codes: list[str] = field(default_factory=list)
    limit: int = 50
    offset: int = 0


@dataclass
class StockPage:
    items: list[Stock]
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
    countries: list[str]
    indices: list[IndexOption]


def _apply_filter(stmt, f: StockFilter):
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
    if f.countries:
        stmt = stmt.where(Stock.country.in_(f.countries))
    if f.index_codes:
        stmt = (
            stmt.join(StockIndex, StockIndex.stock_id == Stock.id)
            .join(Index, Index.id == StockIndex.index_id)
            .where(Index.code.in_(f.index_codes))
            .distinct()
        )
    return stmt


def search_stocks(db: Session, f: StockFilter) -> StockPage:
    limit = max(1, min(f.limit, 500))
    base = select(Stock)
    base = _apply_filter(base, f)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = db.execute(count_stmt).scalar_one()

    rows = db.execute(base.order_by(Stock.ticker).limit(limit + 1).offset(f.offset)).scalars().all()
    has_more = len(rows) > limit
    return StockPage(items=list(rows[:limit]), total=int(total), has_more=has_more)


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
    countries = [
        r[0]
        for r in db.execute(select(distinct(Stock.country)).order_by(Stock.country)).all()
        if r[0]
    ]
    indices = [
        IndexOption(code=row.code, name=row.name)
        for row in db.execute(select(Index).order_by(Index.code)).scalars().all()
    ]
    return FilterOptions(exchanges=exchanges, sectors=sectors, countries=countries, indices=indices)
