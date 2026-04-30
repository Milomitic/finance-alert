"""Idempotent seeding of stocks and index membership from CSV."""
import csv
from dataclasses import dataclass
from typing import IO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex


@dataclass
class SeedResult:
    added: int
    updated: int


def _upsert_stock(db: Session, row: dict[str, str]) -> tuple[Stock, bool]:
    """Return (stock, created)."""
    stmt = select(Stock).where(Stock.ticker == row["ticker"], Stock.exchange == row["exchange"])
    stock = db.execute(stmt).scalar_one_or_none()
    if stock is None:
        stock = Stock(
            ticker=row["ticker"],
            exchange=row["exchange"],
            name=row["name"],
            sector=row.get("sector") or None,
            industry=row.get("industry") or None,
            country=row.get("country") or None,
            currency=row.get("currency") or None,
        )
        db.add(stock)
        db.flush()
        return stock, True
    stock.name = row["name"]
    stock.sector = row.get("sector") or stock.sector
    stock.industry = row.get("industry") or stock.industry
    stock.country = row.get("country") or stock.country
    stock.currency = row.get("currency") or stock.currency
    return stock, False


def _upsert_index(db: Session, code: str, name: str, country: str | None) -> Index:
    idx = db.execute(select(Index).where(Index.code == code)).scalar_one_or_none()
    if idx is None:
        idx = Index(code=code, name=name, country=country)
        db.add(idx)
        db.flush()
    else:
        idx.name = name
        idx.country = country
    return idx


def _ensure_membership(db: Session, stock_id: int, index_id: int) -> None:
    exists = db.execute(
        select(StockIndex).where(StockIndex.stock_id == stock_id, StockIndex.index_id == index_id)
    ).scalar_one_or_none()
    if exists is None:
        db.add(StockIndex(stock_id=stock_id, index_id=index_id))


def seed_index_from_csv(
    db: Session, csv_source: IO[str], *, index_code: str, index_name: str, country: str | None
) -> SeedResult:
    """Upsert stocks from CSV, ensure membership in the named index."""
    idx = _upsert_index(db, index_code, index_name, country)
    added = 0
    updated = 0
    reader = csv.DictReader(csv_source)
    for row in reader:
        _, created = _upsert_stock(db, row)
        added += int(created)
        updated += int(not created)
        # membership requires id; flush already done in _upsert_stock
        stock_id = db.execute(
            select(Stock.id).where(Stock.ticker == row["ticker"], Stock.exchange == row["exchange"])
        ).scalar_one()
        _ensure_membership(db, stock_id, idx.id)
    return SeedResult(added=added, updated=updated)
