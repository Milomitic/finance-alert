"""Refresh `Stock.market_cap` from yfinance.

Used to populate the treemap (mkt-cap × performance). Idempotent: re-running
overwrites with fresh values. Tickers that yfinance can't resolve are skipped
and reported in the result.
"""
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock


@dataclass
class MarketCapRefreshResult:
    stocks_updated: int = 0
    stocks_failed: int = 0
    failed_tickers: list[str] = field(default_factory=list)


def _fetch_market_cap(ticker: str) -> int | None:
    """Wrapped for monkeypatching in tests. Returns market cap (USD/local) or None."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    # fast_info is a dict-like proxy; key may be "market_cap" or "marketCap" depending on
    # yfinance version. Try both. Returns None / 0 / NaN for unknown.
    fi: Any = t.fast_info
    raw: Any = None
    # yfinance 1.x: keys are camelCase ("marketCap"). Older 0.2.x used snake_case
    # ("market_cap"). Try both for forward/backward compat. Use .get() (not [k])
    # because the FastInfo dict raises on unknown keys.
    for key in ("marketCap", "market_cap"):
        try:
            raw = fi.get(key)
            if raw:
                break
        except Exception:  # noqa: BLE001
            continue
    if raw is None:
        return None
    try:
        cap = int(raw)
    except (TypeError, ValueError):
        return None
    return cap if cap > 0 else None


def refresh_market_caps(db: Session) -> MarketCapRefreshResult:
    """Fetch and persist market_cap for every Stock.

    Network-bound (~209 calls × ~0.2s ≈ 40s on a warm cache). Safe to run
    concurrently with scans (uses its own session and only writes one column).
    """
    result = MarketCapRefreshResult()
    stocks = list(db.execute(select(Stock)).scalars().all())
    for stock in stocks:
        try:
            cap = _fetch_market_cap(stock.ticker)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[market_cap] fetch crashed for {stock.ticker}: {e}")
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)
            continue
        if cap is None:
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)
            continue
        stock.market_cap = cap
        result.stocks_updated += 1
    db.commit()
    logger.info(
        f"[market_cap] refresh complete: updated={result.stocks_updated} "
        f"failed={result.stocks_failed}"
    )
    return result
