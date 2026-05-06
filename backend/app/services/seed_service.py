"""Idempotent seeding of stocks and index membership from CSV."""
import csv
from dataclasses import dataclass
from typing import IO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex
from app.services.exchange_codes import canonical_exchange
from app.services.industry_normalizer import canonical_industry
from app.services.sector_normalizer import canonical_sector


@dataclass
class SeedResult:
    added: int
    updated: int


def _upsert_stock(db: Session, row: dict[str, str]) -> tuple[Stock, bool]:
    """Return (stock, created).

    L'exchange del CSV viene canonicalizzato via `canonical_exchange`
    prima di qualsiasi lookup/insert: se in passato (o in un riseed
    futuro con dati legacy) il CSV contenesse "Borsa Italiana" anziché
    "BIT", il valore viene normalizzato a "BIT" così da matchare
    l'invariante DB `UNIQUE(ticker, exchange)` indipendentemente dalla
    sorgente. Senza questo, il seed e il `catalog_refresh_service`
    creavano due righe per lo stesso titolo (vedi
    `scripts/dedupe_stocks.py` per il cleanup storico).
    """
    ticker = row["ticker"]
    exchange = canonical_exchange(ticker, row["exchange"])
    # Sector è normalizzato qui (boundary di ingestion) così le righe
    # nuove non finiscono mai nel DB con labels grezze tipo "Technology"
    # o "Banks" — collassano sempre sui 12 bucket GICS+Other. Vedi
    # `services/sector_normalizer.py`.
    sector_raw = row.get("sector") or None
    sector_canonical = canonical_sector(sector_raw)
    # Industry similarly canonicalized — see `industry_normalizer.py`.
    industry_raw = row.get("industry") or None
    industry_canonical = canonical_industry(industry_raw)
    stmt = select(Stock).where(Stock.ticker == ticker, Stock.exchange == exchange)
    stock = db.execute(stmt).scalar_one_or_none()
    if stock is None:
        stock = Stock(
            ticker=ticker,
            exchange=exchange,
            name=row["name"],
            sector=sector_canonical,
            industry=industry_canonical,
            country=row.get("country") or None,
            currency=row.get("currency") or None,
        )
        db.add(stock)
        db.flush()
        return stock, True
    stock.name = row["name"]
    # Preserve old sector/industry if CSV row has no value (unchanged
    # semantics); otherwise apply the canonical version of the new value.
    stock.sector = sector_canonical or stock.sector
    stock.industry = industry_canonical or stock.industry
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
        stock, created = _upsert_stock(db, row)
        added += int(created)
        updated += int(not created)
        # `_upsert_stock` ha già fatto flush(), quindi `stock.id` è valido.
        # (Storicamente qui si rifaceva una `select(Stock.id) WHERE ticker=
        # AND exchange=row["exchange"]` ma l'exchange grezzo del CSV ora
        # viene canonicalizzato dentro `_upsert_stock`, quindi quella query
        # avrebbe potuto fallire con `scalar_one()` su label legacy. Usare
        # direttamente l'oggetto restituito è più semplice e corretto.)
        _ensure_membership(db, stock.id, idx.id)
    return SeedResult(added=added, updated=updated)
