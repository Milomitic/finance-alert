"""Watchlist business logic."""
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Stock, Watchlist, WatchlistItem


class DuplicateName(Exception):
    pass


@dataclass
class WatchlistSummary:
    id: int
    name: str
    description: str | None
    item_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class WatchlistDetail:
    id: int
    name: str
    description: str | None
    stocks: list[Stock]
    created_at: datetime
    updated_at: datetime


def _exists_by_name(db: Session, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Watchlist.id).where(Watchlist.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Watchlist.id != exclude_id)
    return db.execute(stmt).scalar_one_or_none() is not None


def create_watchlist(db: Session, *, user_id: int, name: str, description: str | None = None) -> Watchlist:
    if _exists_by_name(db, name):
        raise DuplicateName(name)
    wl = Watchlist(user_id=user_id, name=name, description=description)
    db.add(wl)
    db.flush()
    return wl


def list_watchlists(db: Session, *, user_id: int) -> list[WatchlistSummary]:
    stmt = (
        select(Watchlist, func.count(WatchlistItem.stock_id))
        .outerjoin(WatchlistItem, WatchlistItem.watchlist_id == Watchlist.id)
        .where(Watchlist.user_id == user_id)
        .group_by(Watchlist.id)
        .order_by(Watchlist.name)
    )
    return [
        WatchlistSummary(
            id=w.id,
            name=w.name,
            description=w.description,
            item_count=int(cnt),
            created_at=w.created_at,
            updated_at=w.updated_at,
        )
        for w, cnt in db.execute(stmt).all()
    ]


def get_watchlist(db: Session, wl_id: int) -> Watchlist | None:
    return db.execute(select(Watchlist).where(Watchlist.id == wl_id)).scalar_one_or_none()


def get_watchlist_detail(db: Session, wl_id: int) -> WatchlistDetail | None:
    wl = get_watchlist(db, wl_id)
    if wl is None:
        return None
    stocks = (
        db.execute(
            select(Stock)
            .join(WatchlistItem, WatchlistItem.stock_id == Stock.id)
            .where(WatchlistItem.watchlist_id == wl_id)
            .order_by(Stock.ticker)
        )
        .scalars()
        .all()
    )
    return WatchlistDetail(
        id=wl.id,
        name=wl.name,
        description=wl.description,
        stocks=list(stocks),
        created_at=wl.created_at,
        updated_at=wl.updated_at,
    )


def update_watchlist(
    db: Session, wl_id: int, *, name: str | None = None, description: str | None = None
) -> Watchlist | None:
    wl = get_watchlist(db, wl_id)
    if wl is None:
        return None
    if name is not None:
        if _exists_by_name(db, name, exclude_id=wl_id):
            raise DuplicateName(name)
        wl.name = name
    if description is not None:
        wl.description = description
    db.flush()
    return wl


def delete_watchlist(db: Session, wl_id: int) -> bool:
    res = db.execute(delete(Watchlist).where(Watchlist.id == wl_id))
    return res.rowcount > 0


def add_items(db: Session, wl_id: int, stock_ids: list[int]) -> int:
    if not stock_ids:
        return 0
    existing = set(
        db.execute(
            select(WatchlistItem.stock_id).where(
                WatchlistItem.watchlist_id == wl_id,
                WatchlistItem.stock_id.in_(stock_ids),
            )
        )
        .scalars()
        .all()
    )
    new_ids = [sid for sid in stock_ids if sid not in existing]
    db.add_all([WatchlistItem(watchlist_id=wl_id, stock_id=sid) for sid in new_ids])
    db.flush()
    return len(new_ids)


def remove_item(db: Session, wl_id: int, stock_id: int) -> bool:
    res = db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl_id, WatchlistItem.stock_id == stock_id
        )
    )
    return res.rowcount > 0


def bulk_delete_items(db: Session, wl_id: int, stock_ids: list[int]) -> int:
    if not stock_ids:
        return 0
    res = db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl_id,
            WatchlistItem.stock_id.in_(stock_ids),
        )
    )
    return res.rowcount
