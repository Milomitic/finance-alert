"""Regression tests for the stock dedupe migration.

Verifies that:
- duplicate (ticker, exchange) rows are collapsed onto a single canonical row,
- FK references on every related table are reassigned (no CASCADE-loss),
- composite-PK conflicts (e.g. canonical and duplicate both have a bar for
  the same date) are resolved without error,
- the canonical row's exchange label is normalized to the catalog code,
- a second invocation is a no-op.
"""
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Index,
    OhlcvDaily,
    PriceAlert,
    Stock,
    StockIndex,
    User,
)
from app.scripts.dedupe_stocks import (
    canonical_exchange_for,
    dedupe_on_connection,
    pick_canonical,
)


def _seed_dup_pair(
    db: Session,
    ticker: str,
    *,
    canon_exchange: str,
    dup_exchange: str,
    canon_full: bool = True,
) -> tuple[Stock, Stock]:
    """Create a (canonical, duplicate) pair sharing the same ticker."""
    canon = Stock(
        ticker=ticker,
        exchange=canon_exchange,
        name=f"{ticker} canonical",
        sector="Sector A" if canon_full else None,
        industry="Industry A" if canon_full else None,
        country="IT",
        currency="EUR",
    )
    dup = Stock(
        ticker=ticker,
        exchange=dup_exchange,
        name=f"{ticker} duplicate",
        sector=None,
        industry=None,
        country="IT",
        currency="EUR",
    )
    db.add_all([canon, dup])
    db.flush()
    return canon, dup


def test_no_duplicates_when_db_is_clean(db: Session) -> None:
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple"))
    db.flush()

    removed = dedupe_on_connection(db.connection())

    assert removed == 0
    # No same-(ticker, exchange) pair, no same-ticker pair either.
    dups = db.execute(
        text("SELECT ticker, COUNT(*) FROM stocks GROUP BY ticker HAVING COUNT(*) > 1")
    ).fetchall()
    assert dups == []


def test_dedupe_collapses_label_mismatch_pair(db: Session) -> None:
    # Classic case: one row labeled "BIT", another labeled "Borsa Italiana".
    canon, dup = _seed_dup_pair(
        db, "ENEL.MI", canon_exchange="BIT", dup_exchange="Borsa Italiana"
    )

    removed = dedupe_on_connection(db.connection())

    assert removed == 1
    survivors = db.execute(text("SELECT id, ticker, exchange FROM stocks")).fetchall()
    assert len(survivors) == 1
    assert survivors[0][1] == "ENEL.MI"
    # Canonical row kept; exchange already in canonical form.
    assert survivors[0][0] == canon.id
    assert survivors[0][2] == "BIT"


def test_dedupe_relabels_exchange_when_canonical_uses_human_name(db: Session) -> None:
    # The "more complete" row uses the legacy human-readable label.
    canon, dup = _seed_dup_pair(
        db, "ASML.AS",
        canon_exchange="Euronext Amsterdam",  # canonical row
        dup_exchange="AEX",                    # sparse duplicate
        canon_full=True,
    )

    dedupe_on_connection(db.connection())

    # The survivor's exchange must be normalized so the next catalog
    # refresh matches it instead of inserting a 3rd row.
    row = db.execute(
        text("SELECT exchange FROM stocks WHERE ticker = 'ASML.AS'")
    ).scalar_one()
    assert row == "AEX"


def test_dedupe_us_ticker_keeps_existing_exchange_label(db: Session) -> None:
    # AAPL has no recognized suffix → we don't try to guess venue.
    _seed_dup_pair(db, "AAPL", canon_exchange="NASDAQ", dup_exchange="NYSE")

    dedupe_on_connection(db.connection())

    survivors = db.execute(
        text("SELECT exchange FROM stocks WHERE ticker = 'AAPL'")
    ).fetchall()
    assert len(survivors) == 1
    assert survivors[0][0] in {"NASDAQ", "NYSE"}  # whichever was canonical


def test_dedupe_reassigns_alerts_fk(db: Session) -> None:
    canon, dup = _seed_dup_pair(
        db, "ENEL.MI", canon_exchange="BIT", dup_exchange="Borsa Italiana"
    )
    alert = Alert(stock_id=dup.id, trigger_price=10.0, snapshot="{}")
    db.add(alert)
    db.flush()
    alert_id = alert.id

    dedupe_on_connection(db.connection())

    moved = db.execute(
        text("SELECT stock_id FROM alerts WHERE id = :id"), {"id": alert_id}
    ).scalar_one()
    assert moved == canon.id


def test_dedupe_reassigns_price_alerts_fk(db: Session) -> None:
    canon, dup = _seed_dup_pair(
        db, "ENEL.MI", canon_exchange="BIT", dup_exchange="Borsa Italiana"
    )
    pa = PriceAlert(
        stock_id=dup.id,
        direction="above",
        target_price=10.0,
    )
    db.add(pa)
    db.flush()
    pa_id = pa.id

    dedupe_on_connection(db.connection())

    moved = db.execute(
        text("SELECT stock_id FROM price_alerts WHERE id = :id"), {"id": pa_id}
    ).scalar_one()
    assert moved == canon.id


def test_dedupe_merges_stock_indices_without_pk_conflict(db: Session) -> None:
    canon, dup = _seed_dup_pair(
        db, "ENEL.MI", canon_exchange="BIT", dup_exchange="Borsa Italiana"
    )
    idx_a = Index(code="FTSEMIB", name="FTSE MIB", country="IT")
    idx_b = Index(code="EUSTX50", name="EuroStoxx 50", country="EU")
    db.add_all([idx_a, idx_b])
    db.flush()
    # Canonical is in idx_a; dup is in BOTH idx_a (collision) and idx_b (unique).
    db.add_all([
        StockIndex(stock_id=canon.id, index_id=idx_a.id),
        StockIndex(stock_id=dup.id,   index_id=idx_a.id),
        StockIndex(stock_id=dup.id,   index_id=idx_b.id),
    ])
    db.flush()

    dedupe_on_connection(db.connection())

    memberships = sorted(
        r[0] for r in db.execute(
            text("SELECT index_id FROM stock_indices WHERE stock_id = :id"),
            {"id": canon.id},
        )
    )
    assert memberships == sorted([idx_a.id, idx_b.id])
    # No orphan row left on the (now-deleted) duplicate id.
    leftover = db.execute(
        text("SELECT COUNT(*) FROM stock_indices WHERE stock_id = :id"),
        {"id": dup.id},
    ).scalar_one()
    assert leftover == 0


def test_dedupe_merges_ohlcv_overlapping_dates(db: Session) -> None:
    """OHLCV is the highest-volume FK and most likely to hit PK collisions
    (canonical and duplicate both have bars for the same date)."""
    canon, dup = _seed_dup_pair(
        db, "ENEL.MI", canon_exchange="BIT", dup_exchange="Borsa Italiana"
    )
    d1, d2, d3 = date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)
    # Canonical has d1, d2; dup has d2 (collision) and d3 (unique).
    db.add_all([
        OhlcvDaily(stock_id=canon.id, date=d1, open=1, high=1, low=1, close=1, volume=100),
        OhlcvDaily(stock_id=canon.id, date=d2, open=2, high=2, low=2, close=2, volume=200),
        OhlcvDaily(stock_id=dup.id,   date=d2, open=99, high=99, low=99, close=99, volume=999),
        OhlcvDaily(stock_id=dup.id,   date=d3, open=3, high=3, low=3, close=3, volume=300),
    ])
    db.flush()

    dedupe_on_connection(db.connection())

    bars = db.execute(
        text("SELECT date, close FROM ohlcv_daily WHERE stock_id = :id ORDER BY date"),
        {"id": canon.id},
    ).fetchall()
    # Canonical's d2 wins (INSERT OR IGNORE keeps the existing row).
    assert [(str(r[0]), float(r[1])) for r in bars] == [
        (str(d1), 1.0),
        (str(d2), 2.0),  # NOT 99 — canonical's bar was preserved
        (str(d3), 3.0),  # moved over from dup
    ]


def test_dedupe_is_idempotent(db: Session) -> None:
    _seed_dup_pair(db, "ENEL.MI", canon_exchange="BIT", dup_exchange="Borsa Italiana")
    _seed_dup_pair(db, "ASML.AS", canon_exchange="AEX", dup_exchange="Euronext Amsterdam")

    first = dedupe_on_connection(db.connection())
    second = dedupe_on_connection(db.connection())

    assert first == 2
    assert second == 0


def test_no_duplicate_ticker_pairs_after_dedupe(db: Session) -> None:
    """The headline regression assertion."""
    _seed_dup_pair(db, "ENEL.MI", canon_exchange="BIT", dup_exchange="Borsa Italiana")
    _seed_dup_pair(db, "AAPL",    canon_exchange="NASDAQ", dup_exchange="NYSE")
    _seed_dup_pair(db, "ASML.AS", canon_exchange="AEX", dup_exchange="Euronext Amsterdam")

    dedupe_on_connection(db.connection())

    dup_tickers = db.execute(
        text("SELECT ticker, COUNT(*) FROM stocks GROUP BY ticker HAVING COUNT(*) > 1")
    ).fetchall()
    assert dup_tickers == []
    dup_pairs = db.execute(
        text("SELECT ticker, exchange, COUNT(*) FROM stocks "
             "GROUP BY ticker, exchange HAVING COUNT(*) > 1")
    ).fetchall()
    assert dup_pairs == []


def test_pick_canonical_prefers_more_complete_row(db: Session) -> None:
    sparse = Stock(ticker="X.MI", exchange="BIT", name="X")
    full = Stock(
        ticker="X.MI", exchange="Borsa Italiana", name="X",
        sector="S", industry="I", country="IT", currency="EUR", market_cap=1,
    )
    db.add_all([sparse, full])
    db.flush()
    chosen = pick_canonical(db.connection(), [sparse.id, full.id])
    assert chosen == full.id


def test_pick_canonical_tiebreaks_by_lower_id(db: Session) -> None:
    a = Stock(ticker="X.MI", exchange="BIT", name="X", sector="S", industry="I",
              country="IT", currency="EUR", market_cap=1)
    b = Stock(ticker="X.MI", exchange="Borsa Italiana", name="X", sector="S",
              industry="I", country="IT", currency="EUR", market_cap=1)
    db.add_all([a, b])
    db.flush()
    chosen = pick_canonical(db.connection(), [a.id, b.id])
    assert chosen == a.id  # equal scores → lower id wins


def test_canonical_exchange_for_known_suffix() -> None:
    assert canonical_exchange_for("ENEL.MI", "Borsa Italiana") == "BIT"
    assert canonical_exchange_for("ASML.AS", "Euronext Amsterdam") == "AEX"
    assert canonical_exchange_for("BNP.PA", "Euronext Paris") == "EPA"


def test_canonical_exchange_for_unknown_suffix_keeps_current() -> None:
    assert canonical_exchange_for("AAPL", "NASDAQ") == "NASDAQ"
    assert canonical_exchange_for("AAPL", "NYSE") == "NYSE"
