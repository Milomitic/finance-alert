"""Tests for the curated-watchlists bootstrap.

Two behaviours we care about:
  1. **Idempotence**: running the bootstrap twice doesn't duplicate
     watchlists or items.
  2. **Graceful degradation**: tickers not in the catalog are skipped
     with a warning (no crash) — important because curated lists
     reference tickers from many indexes, and seeds may be partial.
"""
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock, User, Watchlist, WatchlistItem
from app.scripts import bootstrap_watchlists


@pytest.fixture
def patched_session(db: Session) -> Iterator[None]:
    """Make `bootstrap_watchlists.SessionLocal()` return the in-memory test
    session instead of the production engine. Wrapped in a no-op close so
    the script's `db.close()` doesn't kill the fixture-managed session."""
    class _Wrap:
        def __init__(self, real: Session) -> None:
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def close(self) -> None:  # bootstrap calls close() in finally
            pass

    with patch.object(bootstrap_watchlists, "SessionLocal", lambda: _Wrap(db)):
        yield


@pytest.fixture
def admin_user(db: Session) -> User:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    return user


def _seed_stocks(db: Session, tickers: list[str]) -> None:
    db.add_all([Stock(ticker=t, exchange="NASDAQ", name=t) for t in tickers])
    db.flush()


def test_bootstrap_creates_watchlists_and_skips_missing_tickers(
    db: Session, admin_user: User, patched_session: None
) -> None:
    # Seed a small subset so most curated tickers will be missing.
    _seed_stocks(db, ["AAPL", "MSFT", "NVDA", "UCG.MI", "ISP.MI"])

    bootstrap_watchlists.ensure_curated_watchlists()
    db.commit()

    # All 12 curated lists exist
    wls = db.execute(select(Watchlist).order_by(Watchlist.name)).scalars().all()
    names = {w.name for w in wls}
    assert "Big Tech US" in names
    assert "Banche italiane" in names
    assert len(wls) == len(bootstrap_watchlists.CURATED)

    # Big Tech US: AAPL, MSFT, NVDA are seeded; the rest were skipped
    big_tech = next(w for w in wls if w.name == "Big Tech US")
    items = (
        db.execute(
            select(Stock.ticker)
            .join(WatchlistItem, WatchlistItem.stock_id == Stock.id)
            .where(WatchlistItem.watchlist_id == big_tech.id)
        )
        .scalars()
        .all()
    )
    assert set(items) == {"AAPL", "MSFT", "NVDA"}

    # Banche italiane: 2 of 5 tickers were seeded → 2 items, no crash
    bi = next(w for w in wls if w.name == "Banche italiane")
    bi_items = (
        db.execute(
            select(Stock.ticker)
            .join(WatchlistItem, WatchlistItem.stock_id == Stock.id)
            .where(WatchlistItem.watchlist_id == bi.id)
        )
        .scalars()
        .all()
    )
    assert set(bi_items) == {"UCG.MI", "ISP.MI"}


def test_bootstrap_is_idempotent(
    db: Session, admin_user: User, patched_session: None
) -> None:
    _seed_stocks(db, ["AAPL", "MSFT", "NVDA"])

    bootstrap_watchlists.ensure_curated_watchlists()
    db.commit()
    first_wl_count = db.execute(select(Watchlist)).scalars().all()
    first_item_count = db.execute(select(WatchlistItem)).scalars().all()

    # Second invocation must not duplicate
    bootstrap_watchlists.ensure_curated_watchlists()
    db.commit()
    second_wl_count = db.execute(select(Watchlist)).scalars().all()
    second_item_count = db.execute(select(WatchlistItem)).scalars().all()

    assert len(first_wl_count) == len(second_wl_count)
    assert len(first_item_count) == len(second_item_count)


def test_bootstrap_with_no_users_is_a_noop(
    db: Session, patched_session: None
) -> None:
    """If the admin user hasn't been provisioned yet, the script logs a
    warning and exits cleanly — must not blow up the bootstrap chain."""
    bootstrap_watchlists.ensure_curated_watchlists()
    db.commit()
    assert db.execute(select(Watchlist)).scalars().all() == []


def test_curated_definitions_are_well_formed() -> None:
    """Catch obvious typos in CURATED at module load: every list has a
    non-empty name, description, and at least one ticker."""
    seen: set[str] = set()
    for c in bootstrap_watchlists.CURATED:
        assert c.name and c.name not in seen, f"duplicate name: {c.name!r}"
        seen.add(c.name)
        assert c.description, f"empty description: {c.name}"
        assert c.tickers, f"empty ticker tuple: {c.name}"
        # Tickers are strings, not accidentally split into chars
        for t in c.tickers:
            assert isinstance(t, str) and len(t) >= 1
