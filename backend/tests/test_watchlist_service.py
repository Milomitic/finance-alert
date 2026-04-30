"""Watchlist service tests."""
import pytest
from sqlalchemy.orm import Session

from app.models import Stock, User
from app.services import watchlist_service as ws


@pytest.fixture
def setup(db: Session) -> tuple[User, Stock, Stock]:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    s1 = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    s2 = Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft")
    db.add_all([s1, s2])
    db.commit()
    return user, s1, s2


def test_create_and_list(db: Session, setup) -> None:
    user, _, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech", description="Tech USA")
    db.commit()
    rows = ws.list_watchlists(db, user_id=user.id)
    assert len(rows) == 1
    assert rows[0].id == wl.id
    assert rows[0].item_count == 0


def test_create_duplicate_name_raises(db: Session, setup) -> None:
    user, _, _ = setup
    ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    with pytest.raises(ws.DuplicateName):
        ws.create_watchlist(db, user_id=user.id, name="Tech")


def test_update(db: Session, setup) -> None:
    user, _, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Old")
    db.commit()
    ws.update_watchlist(db, wl.id, name="New", description="d")
    db.commit()
    refreshed = ws.get_watchlist(db, wl.id)
    assert refreshed.name == "New"
    assert refreshed.description == "d"


def test_delete(db: Session, setup) -> None:
    user, _, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.delete_watchlist(db, wl.id)
    db.commit()
    assert ws.get_watchlist(db, wl.id) is None


def test_add_and_remove_items(db: Session, setup) -> None:
    user, s1, s2 = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.add_items(db, wl.id, [s1.id, s2.id])
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert {s.id for s in detail.stocks} == {s1.id, s2.id}
    ws.remove_item(db, wl.id, s1.id)
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert {s.id for s in detail.stocks} == {s2.id}


def test_add_existing_item_is_idempotent(db: Session, setup) -> None:
    user, s1, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.add_items(db, wl.id, [s1.id])
    db.commit()
    ws.add_items(db, wl.id, [s1.id])
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert len(detail.stocks) == 1


def test_bulk_delete_items(db: Session, setup) -> None:
    user, s1, s2 = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.add_items(db, wl.id, [s1.id, s2.id])
    db.commit()
    ws.bulk_delete_items(db, wl.id, [s1.id, s2.id])
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert detail.stocks == []
