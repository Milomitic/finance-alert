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
    """Wrapped for monkeypatching in tests. Returns market cap in the stock's
    base currency (or None on failure).

    Quirk: yfinance reports LSE-listed stocks (".L") with currency "GBp"
    (pence/penny) instead of "GBP" (pounds). The price IS in pence (e.g.
    HSBA.L last=1359.4 pence) so the marketCap is also in pence. We divide
    by 100 to bring it back to pounds — otherwise HSBA shows ~£23 trillion
    instead of the real ~£233 billion.
    """
    import yfinance as yf

    t = yf.Ticker(ticker)
    fi: Any = t.fast_info
    raw: Any = None
    currency: str | None = None
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
    try:
        currency = fi.get("currency")
    except Exception:  # noqa: BLE001
        currency = None
    if raw is None:
        return None
    try:
        cap = float(raw)
    except (TypeError, ValueError):
        return None
    if cap <= 0:
        return None
    # GBp / GBX (London pence) → divide by 100 to get pounds.
    if currency in ("GBp", "GBX"):
        cap = cap / 100.0
    # Other minor-unit currencies (ZAc cents, ILA agorot, etc.) could be added
    # here as needed; only GBp showed up in our LSE-heavy catalog.
    return int(cap)


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
