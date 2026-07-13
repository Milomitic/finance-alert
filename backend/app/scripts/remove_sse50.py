"""One-shot maintenance: remove the SSE 50 index + its constituent
stocks from the catalog, plus purge every cache layer that may hold
references to those tickers.

Why this exists
───────────────
Originally SSE 50 was seeded to feed the Asia breadth/mood
aggregation while being filtered out of user-facing surfaces (alerts,
screener, search). Per user request the entire surface is now
disabled — the 50 CN stocks bring no incremental value vs HSI30 +
KOSPI20 + N225 already in the Asia bucket, and they consume yfinance
quota on every scan refresh.

What this script touches
────────────────────────
  • `stocks`: deletes every row that is a SSE50 member (matched by
    `stock_indices` join — safer than matching by country='CN' alone
    in case future seeds add CN stocks under a different index).
  • `stock_indices`: cascade — deleted by FK constraint when the
    parent stock row goes.
  • `ohlcv_daily`, `stock_scores`, `alerts`, `price_alerts`,
    `rule_states`: cascade — same.
  • `indices`: deletes the SSE50 row itself.
  • `fetch_cache`: manually purges rows keyed by these tickers
    (no FK to `stocks` so cascades don't reach here).
  • `institutional_holdings`: manually purges rows keyed by these
    tickers (some 13F filings may reference .SS tickers).
  • In-process caches: the run script clears
    `stock_fundamentals_service._CACHE`,
    `stock_news_service._CACHE`,
    Marketaux + Finnhub per-ticker caches.
    These are in-memory only; a backend restart blanks them anyway,
    but clearing here lets a live run not serve stale rows for the
    rest of the session.

Idempotent: re-runs are a no-op once the rows are gone.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.remove_sse50
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Index, Stock

_INDEX_CODE = "SSE50"


def _sse50_tickers(db: Session) -> list[str]:
    """Return the list of tickers that are SSE 50 members. Done as a
    cheap separate query (vs returning Stock objects) because we need
    the strings later to purge non-FK caches (fetch_cache,
    institutional_holdings) AFTER the parent rows are deleted."""
    rows = db.execute(
        text(
            """
            SELECT s.ticker
            FROM stock_indices si
            JOIN stocks s ON s.id = si.stock_id
            JOIN indices i ON i.id = si.index_id
            WHERE i.code = :code
            ORDER BY s.ticker
            """
        ),
        {"code": _INDEX_CODE},
    ).all()
    return [r[0] for r in rows]


def _delete_sse50_stocks(db: Session, tickers: list[str]) -> int:
    """Delete the Stock rows. FK cascades on stock_indices,
    ohlcv_daily, stock_scores, alerts, price_alerts, rule_states.
    Returns the number of rows removed."""
    if not tickers:
        return 0
    rows = db.execute(
        select(Stock).where(Stock.ticker.in_(tickers))
    ).scalars().all()
    for s in rows:
        db.delete(s)
    db.flush()
    return len(rows)


def _sweep_orphan_ss_stocks(db: Session) -> tuple[int, list[str]]:
    """Sweep `.SS`-suffix stocks that have NO index membership — those
    are leftovers from a previous incarnation of SSE 50 / CSI 300 that
    survived index churn. They serve no breadth / mood purpose now
    (orphans don't contribute to any aggregation) and burn yfinance
    quota on every catalog refresh. Strictly speaking these aren't
    SSE 50 members anymore, but they're the same entity-type (CN
    mainland stocks the user asked to retire) so we drop them in the
    same sweep.

    Returns (count_deleted, list_of_tickers) so the caller can extend
    the cache-purge list with these tickers."""
    rows = db.execute(
        text(
            """
            SELECT s.id, s.ticker FROM stocks s
            WHERE s.ticker LIKE '%.SS'
              AND NOT EXISTS (
                SELECT 1 FROM stock_indices si WHERE si.stock_id = s.id
              )
            """
        )
    ).all()
    if not rows:
        return 0, []
    tickers = [r[1] for r in rows]
    ids = [r[0] for r in rows]
    stocks = db.execute(
        select(Stock).where(Stock.id.in_(ids))
    ).scalars().all()
    for s in stocks:
        db.delete(s)
    db.flush()
    return len(stocks), tickers


def _purge_orphan_ss_cache(db: Session) -> int:
    """fetch_cache outlives stocks (no FK) so old `.SS` cache rows
    persist after the stock itself is gone. Sweep any leftovers."""
    result = db.execute(
        text("DELETE FROM fetch_cache WHERE ticker LIKE '%.SS'")
    )
    return result.rowcount or 0


def _delete_index_row(db: Session) -> bool:
    """Drop the `indices.SSE50` row so subsequent `seed.py` runs that
    skip the SSE50 step don't leave an orphan with 0 members in the
    UI selector."""
    idx = db.execute(
        select(Index).where(Index.code == _INDEX_CODE)
    ).scalar_one_or_none()
    if idx is None:
        return False
    db.delete(idx)
    db.flush()
    return True


def _bulk_delete_by_ticker(db: Session, table: str, tickers: list[str]) -> int:
    """Helper: DELETE FROM <table> WHERE ticker IN (...). Uses an
    expanding bindparam so 50+ tickers don't blow the line length or
    expose us to SQL injection via string formatting."""
    if not tickers:
        return 0
    stmt = text(f"DELETE FROM {table} WHERE ticker IN :ts").bindparams(
        bindparam("ts", expanding=True)
    )
    result = db.execute(stmt, {"ts": list(tickers)})
    return result.rowcount or 0


def _purge_fetch_cache(db: Session, tickers: list[str]) -> int:
    """`fetch_cache` has no FK to `stocks` (it's a raw key/value store
    so it can outlive ticker churn). Manual purge here."""
    return _bulk_delete_by_ticker(db, "fetch_cache", tickers)


def _purge_institutional_holdings(db: Session, tickers: list[str]) -> int:
    """Same story as fetch_cache — `institutional_holdings.ticker` is
    a free-form text column, no FK. 13F filings rarely reference .SS
    tickers (US-centric funds), so this is typically a no-op."""
    return _bulk_delete_by_ticker(db, "institutional_holdings", tickers)


def _clear_in_memory_caches(tickers: list[str]) -> None:
    """Drop per-ticker entries from the L1 caches so a running uvicorn
    doesn't keep serving fundamentals/news for SSE50 names until the
    next restart. The L2 (fetch_cache) was already purged above."""
    try:
        from app.services import stock_fundamentals_service as sfs
        for t in tickers:
            sfs._CACHE.pop(t, None)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[remove_sse50] L1 fundamentals clear skipped: {e}")
    try:
        from app.services import stock_news_service as sns
        for t in tickers:
            sns._CACHE.pop(t, None)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[remove_sse50] L1 news clear skipped: {e}")
    try:
        from app.services import marketaux_news_service as mas
        with mas._CACHE_LOCK:
            for t in tickers:
                mas._RESPONSE_CACHE.pop(t, None)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[remove_sse50] Marketaux cache clear skipped: {e}")
    try:
        from app.services import finnhub_news_service as fns
        with fns._CACHE_LOCK:
            for t in tickers:
                fns._NEWS_CACHE.pop(t, None)
                fns._UPGRADE_CACHE.pop(t, None)
                if t in fns._TREND_CACHE:
                    fns._TREND_CACHE.pop(t, None)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[remove_sse50] Finnhub cache clear skipped: {e}")


def run() -> dict[str, int]:
    """Top-level orchestrator. Returns a count summary for logging /
    smoke-testing. Always commits as one transaction — partial state
    here would be confusing on the UI side."""
    db: Session = SessionLocal()
    try:
        tickers = _sse50_tickers(db)
        if not tickers:
            logger.info("[remove_sse50] no SSE50 members in catalog — nothing to do")
            # Still try to clean a dangling index row + fetch_cache rows
            # in case a previous incomplete run left them.

        purged_cache = _purge_fetch_cache(db, tickers)
        purged_hold = _purge_institutional_holdings(db, tickers)
        deleted_stocks = _delete_sse50_stocks(db, tickers)
        # Second pass: orphan .SS stocks (residual rows with no index
        # membership). The cache sweep below will catch their cache
        # rows too — see the docstring on `_sweep_orphan_ss_stocks`.
        orphan_deleted, orphan_tickers = _sweep_orphan_ss_stocks(db)
        orphan_cache_purged = _purge_orphan_ss_cache(db)
        deleted_index = _delete_index_row(db)
        db.commit()

        _clear_in_memory_caches(tickers + orphan_tickers)

        summary = {
            "tickers_matched": len(tickers),
            "stocks_deleted": deleted_stocks,
            "orphan_ss_stocks_deleted": orphan_deleted,
            "orphan_ss_tickers": orphan_tickers,
            "index_row_deleted": int(deleted_index),
            "fetch_cache_purged": purged_cache,
            "orphan_ss_cache_purged": orphan_cache_purged,
            "institutional_holdings_purged": purged_hold,
        }
        logger.info(f"[remove_sse50] done: {summary}")
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    summary = run()
    print(summary)
