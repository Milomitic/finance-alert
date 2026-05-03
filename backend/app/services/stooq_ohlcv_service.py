"""Stooq OHLCV fallback (no API key required, CSV over HTTPS).

Used when the yfinance circuit breaker is OPEN. Stooq covers most US/EU/UK
tickers, with a slightly different naming convention (lowercase, dot suffix
mapped to local exchange suffix). Mapping table is best-effort — a fetch
miss is non-fatal: caller will skip the stock for this scan cycle.

Endpoint shape:
    https://stooq.com/q/d/l/?s=aapl.us&d1=20240101&d2=20251231&i=d
returns CSV: Date,Open,High,Low,Close,Volume (header + N rows, ascending).
"""
import io
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd
from loguru import logger


# yfinance suffix → stooq suffix
_SUFFIX_MAP: dict[str, str] = {
    "":   "us",      # bare → US
    "L":  "uk",      # London
    "MI": "it",      # Milan
    "DE": "de",      # Frankfurt (Xetra)
    "PA": "fr",      # Paris
    "AS": "nl",      # Amsterdam
    "BR": "be",      # Brussels
    "MC": "es",      # Madrid
    "SW": "ch",      # Swiss
    "HE": "fi",      # Helsinki
    "CO": "dk",      # Copenhagen
    "IR": "ie",      # Irish
    "HK": "hk",      # Hong Kong
    "SS": None,      # Shanghai — Stooq has no clean prefix; fallback unavailable
    "SZ": None,      # Shenzhen — same
}


def _stooq_symbol(yf_ticker: str) -> str | None:
    """Map a yfinance-style ticker to a Stooq symbol, or None if unmappable."""
    base, _, suffix = yf_ticker.partition(".")
    suffix = suffix.upper()
    stooq_suffix = _SUFFIX_MAP.get(suffix, "us") if suffix else "us"
    if stooq_suffix is None:
        return None
    return f"{base.lower()}.{stooq_suffix}"


def _parse_csv(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text))
    if "Date" not in df.columns:
        return pd.DataFrame()
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df.rename(columns=str.lower, inplace=True)
    return df


def _fetch_stooq_csv(symbol: str, days: int = 365) -> pd.DataFrame | None:
    """HTTP GET the Stooq CSV. Returns None on any HTTP/parse error."""
    import requests

    end = date.today()
    start = end - timedelta(days=days)
    url = (
        f"https://stooq.com/q/d/l/?s={symbol}"
        f"&d1={start.strftime('%Y%m%d')}&d2={end.strftime('%Y%m%d')}&i=d"
    )
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "FinanceAlert/0.1"})
        r.raise_for_status()
        text = r.text.strip()
        # Stooq returns "No data" plain text on misses
        if not text or text.startswith("No data"):
            return None
        df = _parse_csv(text)
        if df.empty or "close" not in df.columns:
            return None
        return df
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[stooq] fetch {symbol} failed: {exc}")
        return None


@dataclass
class StooqResult:
    rows_inserted: int = 0
    stocks_succeeded: int = 0
    stocks_failed: int = 0
    failed_tickers: list[str] = field(default_factory=list)


def fetch_one(yf_ticker: str, days: int = 365) -> pd.DataFrame | None:
    """Public single-ticker fetch. Returns a DataFrame with columns
    [date, open, high, low, close, volume] in chronological order, or None."""
    symbol = _stooq_symbol(yf_ticker)
    if symbol is None:
        return None
    df = _fetch_stooq_csv(symbol, days=days)
    if df is None:
        return None
    # Normalize to the column order our upsert helpers expect
    expected = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        logger.debug(f"[stooq] missing cols for {symbol}: {missing}")
        return None
    df = df[expected].dropna(subset=["close"])
    return df.reset_index(drop=True)


def upsert_via_stooq(db: Any, stocks: list[Any], *, days: int = 365) -> StooqResult:
    """Drop-in replacement for ohlcv_service.fetch_and_upsert that uses Stooq.

    Iterates per-ticker (Stooq doesn't have a batch endpoint), calls the
    same upsert helper as the yfinance path. Best-effort — unmappable
    tickers (e.g. .SS Shanghai) are silently skipped.
    """
    from app.services.ohlcv_service import _upsert_one_stock  # private helper reuse

    result = StooqResult()
    for stock in stocks:
        df = fetch_one(stock.ticker, days=days)
        if df is None or df.empty:
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)
            continue
        # _upsert_one_stock expects yfinance-shaped frame indexed by date with
        # columns Open/High/Low/Close/Volume. Map case + index.
        frame = df.set_index("date")
        frame.columns = [c.capitalize() for c in frame.columns]
        try:
            inserted, _updated = _upsert_one_stock(db, stock, frame)
            result.rows_inserted += inserted
            result.stocks_succeeded += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[stooq] upsert failed for {stock.ticker}: {exc}")
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)
    logger.info(
        f"[stooq] fallback complete: ok={result.stocks_succeeded} "
        f"fail={result.stocks_failed} rows={result.rows_inserted}"
    )
    return result
