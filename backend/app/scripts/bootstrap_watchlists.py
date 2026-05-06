"""Idempotent bootstrap of curated default watchlists.

The user wants ready-to-consult lists by topic/sector ("watchlist
quando mi interessano ambiti o settori particolari") instead of
having to assemble them by hand from the screener every time.

Design notes
------------
- Curated lists are owned by the **admin user** (id=1). They show up
  alongside any user-created watchlists.
- Each list is keyed by `name`; running the script twice doesn't
  duplicate. New tickers added to `CURATED` flow into the existing
  watchlist on rerun (we don't prune — user-added items survive).
- Tickers that aren't in the catalog are silently skipped, with a
  warning log. This means a list like "Trading houses giapponesi"
  works only after the Nikkei seed is in place — graceful degradation
  for partial seeds.
- The catalog has duplicate ticker rows for ~59 securities (see
  CLAUDE.md). We pick *any* matching row — read-only consumers don't
  care which one, and `.limit(1)` keeps us from raising
  `MultipleResultsFound`.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.bootstrap_watchlists
Or it runs automatically as part of `app.scripts.bootstrap.main()`.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Stock, User, Watchlist, WatchlistItem


@dataclass(frozen=True)
class CuratedList:
    name: str
    description: str
    tickers: tuple[str, ...]


# Curated taxonomy. Each list addresses one investing theme so the user
# can jump in and skim it without rebuilding a screener every time.
# Tickers that aren't in the catalog are skipped at apply time.
CURATED: tuple[CuratedList, ...] = (
    CuratedList(
        name="Big Tech US",
        description=(
            "Magnificent 7 + Netflix — i mega-cap tech USA che muovono "
            "S&P 500 e Nasdaq."
        ),
        tickers=(
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX",
        ),
    ),
    CuratedList(
        name="AI & Semiconduttori",
        description=(
            "Pure-play sui chip e fornitori chiave per l'intelligenza "
            "artificiale (NVIDIA, AMD, ASML, Broadcom, ARM, …)."
        ),
        tickers=(
            "NVDA", "AMD", "AVGO", "ASML", "INTC", "MU", "QCOM", "ARM",
        ),
    ),
    CuratedList(
        name="Banche italiane",
        description=(
            "I principali istituti del FTSE MIB: Unicredit, Intesa, "
            "Banco BPM, MPS, Mediobanca."
        ),
        tickers=(
            "UCG.MI", "ISP.MI", "BAMI.MI", "BMPS.MI", "MB.MI",
        ),
    ),
    CuratedList(
        name="Lusso & Made in Italy",
        description=(
            "Nomi italiani del lusso/luxury industriale (Ferrari, "
            "Moncler) e listed-in-Milan emblematici."
        ),
        tickers=(
            "RACE.MI", "MONC.MI", "STLAM.MI", "LDO.MI",
        ),
    ),
    CuratedList(
        name="Energia & Oil",
        description=(
            "Major globali del petrolio + Eni, per esposizione al ciclo "
            "energetico."
        ),
        tickers=(
            "XOM", "CVX", "COP", "OXY", "SLB", "ENI.MI",
        ),
    ),
    CuratedList(
        name="Big Pharma",
        description=(
            "Mega-cap farmaceutici USA: rivelano la salute del settore "
            "healthcare globale."
        ),
        tickers=(
            "JNJ", "PFE", "LLY", "MRK", "ABBV", "BMY", "AMGN", "GILD", "UNH",
        ),
    ),
    CuratedList(
        name="Auto & Mobilità",
        description=(
            "Costruttori auto USA + Stellantis + i giapponesi del Nikkei "
            "(Toyota, Honda, Suzuki, Subaru) + Ferrari."
        ),
        tickers=(
            "TSLA", "F", "GM", "STLAM.MI", "RACE.MI",
            "7203.T", "7267.T", "7269.T", "7270.T",
        ),
    ),
    CuratedList(
        name="Trading houses giapponesi",
        description=(
            "Le 'sōgō shōsha' — conglomerate diversificate iconiche "
            "(Itochu, Mitsubishi, Mitsui, Sumitomo, Marubeni). Buffett "
            "ne è grosso azionista."
        ),
        tickers=(
            "8001.T", "8058.T", "8031.T", "8053.T", "8002.T",
        ),
    ),
    CuratedList(
        name="Difesa & Aerospazio",
        description=(
            "Prime contractor della difesa USA + Leonardo (FTSE MIB)."
        ),
        tickers=(
            "LMT", "RTX", "NOC", "GD", "BA", "LDO.MI",
        ),
    ),
    CuratedList(
        name="Banche USA",
        description=(
            "Big 6 banche americane: i bellwether del credito globale."
        ),
        tickers=(
            "JPM", "BAC", "WFC", "C", "GS", "MS",
        ),
    ),
    CuratedList(
        name="Consumer Staples globali",
        description=(
            "Beni di largo consumo difensivi: Coca-Cola, Pepsi, P&G, "
            "Walmart, Costco."
        ),
        tickers=(
            "KO", "PEP", "PG", "WMT", "COST",
        ),
    ),
    CuratedList(
        name="Pagamenti & Fintech",
        description=(
            "Reti carte (Visa, Mastercard, Amex) e fintech. Termometro "
            "dei consumi e del ciclo economico."
        ),
        tickers=(
            "V", "MA", "AXP", "PYPL",
        ),
    ),
)


def _admin_user_id(db: Session) -> int | None:
    row = db.execute(select(User.id).order_by(User.id).limit(1)).scalar_one_or_none()
    return int(row) if row is not None else None


def _resolve_stock_ids(db: Session, tickers: tuple[str, ...]) -> tuple[list[int], list[str]]:
    """Return (resolved_ids, missing_tickers). Picks any matching row when
    duplicates exist (see CLAUDE.md note on duplicate ticker rows)."""
    resolved: list[int] = []
    missing: list[str] = []
    for t in tickers:
        sid = db.execute(
            select(Stock.id).where(Stock.ticker == t).limit(1)
        ).scalar_one_or_none()
        if sid is None:
            missing.append(t)
        else:
            resolved.append(int(sid))
    return resolved, missing


def _upsert_watchlist(
    db: Session, *, user_id: int, name: str, description: str
) -> Watchlist:
    wl = db.execute(select(Watchlist).where(Watchlist.name == name)).scalar_one_or_none()
    if wl is None:
        wl = Watchlist(user_id=user_id, name=name, description=description)
        db.add(wl)
        db.flush()
        return wl
    # Refresh description in case the curated copy was edited; leave name and
    # owner alone so user customisations on the row aren't blown away.
    wl.description = description
    return wl


def _add_missing_items(db: Session, wl_id: int, stock_ids: list[int]) -> int:
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
    if not new_ids:
        return 0
    db.add_all([WatchlistItem(watchlist_id=wl_id, stock_id=sid) for sid in new_ids])
    db.flush()
    return len(new_ids)


def ensure_curated_watchlists() -> None:
    db = SessionLocal()
    try:
        user_id = _admin_user_id(db)
        if user_id is None:
            logger.warning(
                "No users yet — skipping curated watchlist bootstrap. "
                "Run `set_admin_password` first."
            )
            return

        total_added = 0
        for c in CURATED:
            wl = _upsert_watchlist(
                db, user_id=user_id, name=c.name, description=c.description
            )
            stock_ids, missing = _resolve_stock_ids(db, c.tickers)
            added = _add_missing_items(db, wl.id, stock_ids)
            total_added += added
            if missing:
                logger.warning(
                    f"Watchlist '{c.name}': {len(missing)} ticker(s) "
                    f"not in catalog, skipped: {missing}"
                )
            logger.info(
                f"Watchlist '{c.name}': {len(stock_ids)} resolved, "
                f"{added} newly added"
            )
        db.commit()
        logger.info(
            f"Curated watchlists bootstrap complete: {len(CURATED)} lists, "
            f"{total_added} new items inserted"
        )
    finally:
        db.close()


if __name__ == "__main__":
    ensure_curated_watchlists()
