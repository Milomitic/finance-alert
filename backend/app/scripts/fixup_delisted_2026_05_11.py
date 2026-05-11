"""One-shot catalog maintenance — 2026-05-11 audit of delisted/renamed tickers.

Found 10 tickers in the catalog that yfinance's fast_info couldn't resolve.
Investigation result, per-ticker:

- BRK.B, BF.B, BT.A     → Yahoo uses hyphen (BRK-B, BF-B, BT-A.L) for
                          class-letter shares, not period. UPDATE ticker.
- DPW.DE                → Deutsche Post AG renamed to DHL Group in 2023;
                          new ticker DHL.DE. UPDATE ticker + name.
- CRG.IR                → CRH plc moved primary listing from Dublin to NYSE
                          in 2023. New primary CRH (NYSE, USD). UPDATE.
- FLTR.IR               → Flutter Entertainment moved primary listing to
                          NYSE 2024 as FLUT. UPDATE.
- STM.MI                → STMicroelectronics .MI listing returns no data;
                          NYSE listing STM (USD) is alive. UPDATE.
- US.MI                 → Unipol Gruppo renamed to Unipol Assicurazioni
                          (UNI.MI). UPDATE.
- 0011.HK               → Hang Lung Group — yfinance can't resolve any
                          alternate; treat as dead in our feed. DELETE.
- WBA                   → Walgreens Boots Alliance taken private by
                          Sycamore Partners (deal closed early 2025).
                          DELETE.

Run with: ./.venv/Scripts/python.exe -m app.scripts.fixup_delisted_2026_05_11

Idempotent: re-running after success is a no-op (UPDATE skips when the
old ticker is already gone, DELETE skips when the row is already gone).
Preserves all FK references via UPDATE (alerts, ohlcv_daily, watchlists,
etc. follow the new ticker). DELETE relies on the existing CASCADE rules
on Stock.id.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services.exchange_codes import canonical_exchange


@dataclass(frozen=True)
class Rename:
    old_ticker: str
    new_ticker: str
    new_name: str | None = None
    new_exchange: str | None = None
    new_country: str | None = None
    new_currency: str | None = None


RENAMES = [
    # Class-letter ticker format (Yahoo: hyphen, not period)
    Rename("BRK.B", "BRK-B"),
    Rename("BF.B", "BF-B"),
    Rename("BT.A", "BT-A.L"),
    # Corporate rename
    Rename("DPW.DE", "DHL.DE", new_name="DHL Group"),
    # Primary listing relocations
    Rename(
        "CRG.IR", "CRH",
        new_name="CRH plc",
        new_exchange="NYSE", new_country="IE", new_currency="USD",
    ),
    Rename(
        "FLTR.IR", "FLUT",
        new_name="Flutter Entertainment plc",
        new_exchange="NYSE", new_country="IE", new_currency="USD",
    ),
    Rename(
        "STM.MI", "STM",
        new_name="STMicroelectronics N.V.",
        new_exchange="NYSE", new_country="CH", new_currency="USD",
    ),
    Rename(
        "US.MI", "UNI.MI",
        new_name="Unipol Assicurazioni S.p.A.",
        new_exchange="BIT", new_country="IT", new_currency="EUR",
    ),
]

TRULY_DELISTED = [
    "0011.HK",   # Hang Lung Group — no resolvable alternate on yfinance
    "WBA",       # Walgreens Boots Alliance — taken private 2025
]


# Intra-DB duplicate-ticker collapses. Some tickers ended up in two rows on
# different exchanges as a side effect of corporate relocations + index
# seed re-runs. We keep ONE row (the one whose exchange matches yfinance's
# primary listing today) and drop the stale row + its FK chain.
INTRA_DUPLICATES_TO_RESOLVE = {
    # ticker: keep_exchange (the canonical/yfinance-resolvable one)
    "CRH": "NYSE",   # CRH plc primary listing moved Dublin -> NYSE in 2023.
                      # The NASDAQ row was a vestigial entry; NYSE is the
                      # current truth (eustx50.csv was patched to NYSE).
}


def run() -> None:
    db = SessionLocal()
    n_renamed = 0
    n_collapsed_into_existing = 0
    n_duplicate_old_rows_dropped = 0
    n_deleted = 0
    try:
        for r in RENAMES:
            old_rows = db.execute(
                select(Stock).where(Stock.ticker == r.old_ticker)
            ).scalars().all()
            if not old_rows:
                logger.info(f"rename skipped (already gone): {r.old_ticker}")
                continue
            # Catalog has duplicate-ticker rows for some tickers (CLAUDE.md)
            # — same ticker on different exchanges. If old_rows has >1, we
            # rename ONE and drop the rest (cascade clears their FK chains).
            target_existing = db.execute(
                select(Stock).where(Stock.ticker == r.new_ticker).limit(1)
            ).scalar_one_or_none()
            target_exchange = (
                canonical_exchange(r.new_ticker, r.new_exchange)
                if r.new_exchange else None
            )
            if target_existing is not None:
                # New ticker already in catalog (e.g. UNI.MI from FTSEMIB
                # seed, DHL.DE from EUSTX50). Collapse ALL old rows into
                # the existing canonical one — cascade drops their FKs.
                for stock in old_rows:
                    logger.info(
                        f"collapsing {r.old_ticker} (stock_id={stock.id}) into "
                        f"existing {r.new_ticker} (stock_id={target_existing.id})"
                    )
                    db.delete(stock)
                    n_collapsed_into_existing += 1
                continue
            # No target row → rename the FIRST old row in place (preserves
            # OHLCV history + alerts + scores), drop any duplicates so we
            # don't trip the UNIQUE(ticker, exchange) constraint when both
            # would become the same new ticker.
            for i, stock in enumerate(old_rows):
                if i == 0:
                    stock.ticker = r.new_ticker
                    if r.new_name is not None:
                        stock.name = r.new_name
                    if target_exchange is not None:
                        stock.exchange = target_exchange
                    if r.new_country is not None:
                        stock.country = r.new_country
                    if r.new_currency is not None:
                        stock.currency = r.new_currency
                    logger.info(
                        f"renamed {r.old_ticker} -> {r.new_ticker} "
                        f"(stock_id={stock.id})"
                    )
                    n_renamed += 1
                else:
                    logger.info(
                        f"dropping duplicate old row {r.old_ticker} "
                        f"(stock_id={stock.id}) — first row was renamed to "
                        f"{r.new_ticker}"
                    )
                    db.delete(stock)
                    n_duplicate_old_rows_dropped += 1
            # Flush so the UNIQUE(ticker, exchange) constraint sees the
            # rename + deletes BEFORE we proceed to the next rename in the
            # loop. Without the flush, a second rename that would touch the
            # same target ticker could race the un-flushed delete.
            db.flush()
        # Resolve intra-DB duplicates (same ticker on different exchanges
        # where one is stale).
        for ticker, keep_exchange in INTRA_DUPLICATES_TO_RESOLVE.items():
            rows = db.execute(
                select(Stock).where(Stock.ticker == ticker)
            ).scalars().all()
            if len(rows) <= 1:
                continue
            keepers = [r for r in rows if r.exchange == keep_exchange]
            droppers = [r for r in rows if r.exchange != keep_exchange]
            if not keepers:
                logger.warning(
                    f"intra-duplicate cleanup skipped for {ticker}: "
                    f"no row matches keep_exchange={keep_exchange!r}"
                )
                continue
            for stock in droppers:
                logger.info(
                    f"dropping intra-duplicate {ticker} stock_id={stock.id} "
                    f"exchange={stock.exchange!r} (keeping "
                    f"stock_id={keepers[0].id} exchange={keep_exchange!r})"
                )
                db.delete(stock)
        for ticker in TRULY_DELISTED:
            rows = db.execute(
                select(Stock).where(Stock.ticker == ticker)
            ).scalars().all()
            if not rows:
                logger.info(f"delete skipped (already gone): {ticker}")
                continue
            for stock in rows:
                logger.info(
                    f"deleted truly-delisted {ticker} (stock_id={stock.id})"
                )
                db.delete(stock)
                n_deleted += 1
        db.commit()
        logger.info(
            f"DONE: renamed={n_renamed} "
            f"collapsed_into_existing={n_collapsed_into_existing} "
            f"duplicate_old_rows_dropped={n_duplicate_old_rows_dropped} "
            f"deleted={n_deleted}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    run()
