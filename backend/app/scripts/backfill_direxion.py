"""One-shot backfill OHLCV + fundamentals + scores for the new
Direxion Daily ETF tickers we just seeded."""
from app.core.db import SessionLocal
from app.models import Index, Stock, StockIndex
from app.services import ohlcv_service, score_service, stock_fundamentals_service
from sqlalchemy import select
from loguru import logger


def main():
    db = SessionLocal()
    try:
        # Pull the Direxion index members
        idx = db.execute(select(Index).where(Index.code == "DIREXION")).scalar_one()
        rows = db.execute(
            select(Stock)
            .join(StockIndex, StockIndex.stock_id == Stock.id)
            .where(StockIndex.index_id == idx.id)
        ).scalars().all()
        # Dedupe by ticker (catalog has duplicates per CLAUDE.md)
        seen = set()
        stocks = []
        for s in rows:
            if s.ticker in seen:
                continue
            seen.add(s.ticker)
            stocks.append(s)
        logger.info(f"Backfilling {len(stocks)} Direxion ETFs")

        # 1. OHLCV (5y for chart depth + indicator warmup)
        logger.info("Step 1/3: OHLCV backfill (5y)")
        result = ohlcv_service.fetch_and_upsert(db, stocks, period="5y")
        logger.info(f"OHLCV: rows_inserted={result.rows_inserted} ok={result.stocks_succeeded} fail={result.stocks_failed}")
        if result.failed_tickers:
            logger.warning(f"Failed tickers: {result.failed_tickers}")

        # 2. Fundamentals warmup (best-effort; ETFs may not have full fundamentals)
        logger.info("Step 2/3: Fundamentals warmup")
        ok = fail = 0
        for s in stocks:
            try:
                f = stock_fundamentals_service.get_fundamentals(s.ticker)
                if f is not None:
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                logger.debug(f"fundamentals failed {s.ticker}: {e}")
                fail += 1
        logger.info(f"Fundamentals: ok={ok} fail={fail}")

        # 3. Score recompute (uses sector_stats — Direxion sector is mostly
        # 'Other' so will fall back to universe medians)
        logger.info("Step 3/3: Score recompute (per ETF)")
        ok = fail = 0
        for s in stocks:
            try:
                score = score_service.compute_score(db, s)
                db.merge(score)
                db.commit()
                ok += 1
            except Exception as e:
                logger.debug(f"score failed {s.ticker}: {e}")
                db.rollback()
                fail += 1
        logger.info(f"Scores: ok={ok} fail={fail}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
