"""Refresh stock catalog from Wikipedia constituent tables."""
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CatalogRefreshLog, Index, Stock, StockIndex

USER_AGENT = "FinanceAlert/0.1 (personal use)"

INDEX_SOURCES: dict[str, dict[str, object]] = {
    "SP500": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "name": "S&P 500",
        "country": "US",
        "table_index": 0,
        "ticker_col": "Symbol",
        "name_col": "Security",
        "sector_col": "GICS Sector",
        "industry_col": "GICS Sub-Industry",
        "default_exchange": "NASDAQ",
        "currency": "USD",
    },
    "NDX": {
        # As of 2026, Wikipedia constituents table moved to index 5 and uses
        # ICB classification columns instead of GICS.
        "url": "https://en.wikipedia.org/wiki/Nasdaq-100",
        "name": "Nasdaq-100",
        "country": "US",
        "table_index": 5,
        "ticker_col": "Ticker",
        "name_col": "Company",
        "sector_col": "ICB Industry[14]",
        "industry_col": "ICB Subsector[14]",
        "default_exchange": "NASDAQ",
        "currency": "USD",
    },
    "DJI": {
        "url": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
        "name": "Dow Jones Industrial Average",
        "country": "US",
        "table_index": 1,
        "ticker_col": "Symbol",
        "name_col": "Company",
        "sector_col": "Industry",
        "industry_col": None,
        "default_exchange": "NYSE",
        "currency": "USD",
    },
    # FTSEMIB rimosso a favore di FTSE100 (UK): le poche italiane di interesse
    # restano coperte da EUSTX50 (Stellantis, Enel, ENI, Intesa, UniCredit).
    "EUSTX50": {
        # Constituents now at table index 3.
        "url": "https://en.wikipedia.org/wiki/EURO_STOXX_50",
        "name": "EuroStoxx 50",
        "country": "EU",
        "table_index": 3,
        "ticker_col": "Ticker",
        "name_col": "Name",
        "sector_col": "ICB Sector",
        "industry_col": None,
        "default_exchange": "XETRA",
        "currency": "EUR",
    },
    "SSE50": {
        "url": "https://en.wikipedia.org/wiki/SSE_50_Index",
        "name": "SSE 50",
        "country": "CN",
        "table_index": 1,
        "ticker_col": "Ticker symbol",
        "name_col": "Name",
        "sector_col": "Industry",
        "industry_col": None,
        "default_exchange": "SSE",
        "currency": "CNY",
    },
    "HSI30": {
        # Code kept as HSI30 for backward-compat with snapshots/alerts; display
        # name now reflects the wider top-50 cut. Constituents table is at
        # index 6 in the current Wikipedia layout (was 5 in 2025).
        "url": "https://en.wikipedia.org/wiki/Hang_Seng_Index",
        "name": "Hang Seng top 50",
        "country": "HK",
        "table_index": 6,
        "ticker_col": "Ticker",
        "name_col": "Name",
        "sector_col": "Sub-index",
        "industry_col": None,
        "default_exchange": "HKEX",
        "currency": "HKD",
        "slice_n": 50,
    },
    "CSI300": {
        "url": "https://en.wikipedia.org/wiki/CSI_300_Index",
        "name": "CSI 300 (Shanghai + Shenzhen)",
        "country": "CN",
        "table_index": 3,
        "ticker_col": "Ticker",
        "name_col": "Company",
        "sector_col": "Segment",
        "industry_col": None,
        "default_exchange": "SSE",
        "currency": "CNY",
    },
    "FTSE100": {
        "url": "https://en.wikipedia.org/wiki/FTSE_100_Index",
        "name": "FTSE 100 (London)",
        "country": "GB",
        "table_index": 6,
        "ticker_col": "Ticker",
        "name_col": "Company",
        "sector_col": "FTSE industry classification benchmark sector[39]",
        "industry_col": None,
        "default_exchange": "LSE",
        "currency": "GBP",
        # No slice_n — take all 100 components.
    },
}


@dataclass
class RefreshResult:
    index_code: str
    status: str
    stocks_added: int = 0
    stocks_updated: int = 0
    stocks_removed: int = 0
    error_message: str | None = None


def _fetch_table(url: str, table_index: int) -> pd.DataFrame:
    """Wrap pandas.read_html with retry. Patchable for tests."""
    last: Exception | None = None
    for attempt, delay in enumerate([0, 30, 120]):
        if delay:
            time.sleep(delay)
        try:
            tables = pd.read_html(url, storage_options={"User-Agent": USER_AGENT})
            return tables[table_index]
        except Exception as e:  # noqa: BLE001
            last = e
            logger.warning(f"read_html failed for {url} (attempt {attempt + 1}): {e}")
    assert last is not None
    raise last


def _normalize_ticker(raw: str, default_exchange: str) -> tuple[str, str]:
    """Map ticker suffix to exchange code; fall back to default_exchange.

    For CSI 300 entries that come as "SSE: 600519" or "SZSE: 002475", strip
    the prefix and append the proper yfinance suffix.

    For LSE-default tickers without a suffix, append ".L" so yfinance resolves
    them on London (FTSE 100 entries are listed bare on Wikipedia).
    """
    t = str(raw).strip().upper()
    # CSI 300: "SSE: 600519" / "SZSE: 002475"
    if t.startswith("SSE:") or t.startswith("SZSE:"):
        prefix, _, num = t.partition(":")
        num = num.strip()
        if prefix == "SSE":
            return f"{num}.SS", "SSE"
        return f"{num}.SZ", "SZSE"
    suffix_to_exchange = {
        ".MI": "BIT",      # Borsa Italiana
        ".DE": "XETRA",    # Deutsche Boerse
        ".PA": "EPA",      # Euronext Paris
        ".AS": "AEX",      # Amsterdam
        ".SW": "SIX",      # Swiss
        ".CO": "CSE",      # Copenhagen
        ".HE": "HEL",      # Helsinki
        ".BR": "BRU",      # Brussels
        ".MC": "BME",      # Madrid
        ".IR": "ISE",      # Irish
        ".SS": "SSE",      # Shanghai
        ".SZ": "SZSE",     # Shenzhen
        ".HK": "HKEX",     # Hong Kong
        ".L":  "LSE",      # London Stock Exchange
    }
    for suffix, exchange in suffix_to_exchange.items():
        if t.endswith(suffix):
            return t, exchange
    # LSE-default tickers without explicit suffix → append .L for yfinance
    if default_exchange == "LSE" and "." not in t:
        return f"{t}.L", "LSE"
    return t, default_exchange


def _start_log(db: Session, index_code: str) -> CatalogRefreshLog:
    log = CatalogRefreshLog(index_code=index_code, status="in_progress")
    db.add(log)
    db.flush()
    return log


def _finalize_log(log: CatalogRefreshLog, result: RefreshResult) -> None:
    log.status = result.status
    log.stocks_added = result.stocks_added
    log.stocks_updated = result.stocks_updated
    log.stocks_removed = result.stocks_removed
    log.error_message = result.error_message
    log.completed_at = datetime.now(UTC)


def _ensure_index(db: Session, code: str, name: str, country: str) -> Index:
    idx = db.execute(select(Index).where(Index.code == code)).scalar_one_or_none()
    if idx is None:
        idx = Index(code=code, name=name, country=country)
        db.add(idx)
        db.flush()
    return idx


def refresh_index(db: Session, index_code: str) -> RefreshResult:
    if index_code not in INDEX_SOURCES:
        raise KeyError(index_code)
    src = INDEX_SOURCES[index_code]
    log = _start_log(db, index_code)
    result = RefreshResult(index_code=index_code, status="in_progress")
    try:
        df = _fetch_table(str(src["url"]), int(src["table_index"]))  # type: ignore[arg-type]
        # Optional top-N slice (e.g., HSI30 takes top 30 of more constituents)
        slice_n = src.get("slice_n")
        if slice_n is not None:
            df = df.head(int(slice_n))
        idx = _ensure_index(db, index_code, str(src["name"]), str(src["country"]))
        added = updated = 0
        seen_stock_ids: set[int] = set()
        for _, row in df.iterrows():
            ticker_raw = row.get(src["ticker_col"])
            if pd.isna(ticker_raw):
                continue
            ticker, exchange = _normalize_ticker(ticker_raw, str(src["default_exchange"]))
            name_val = str(row.get(src["name_col"]) or ticker)
            sector_val = (
                str(row.get(src["sector_col"]))
                if src["sector_col"] and not pd.isna(row.get(src["sector_col"]))
                else None
            )
            industry_col = src.get("industry_col")
            industry_val = (
                str(row.get(industry_col))
                if industry_col and not pd.isna(row.get(industry_col))
                else None
            )
            stmt = select(Stock).where(Stock.ticker == ticker, Stock.exchange == exchange)
            stock = db.execute(stmt).scalar_one_or_none()
            if stock is None:
                stock = Stock(
                    ticker=ticker,
                    exchange=exchange,
                    name=name_val,
                    sector=sector_val,
                    industry=industry_val,
                    country=str(src["country"]),
                    currency=str(src["currency"]),
                )
                db.add(stock)
                db.flush()
                added += 1
            else:
                stock.name = name_val
                if sector_val:
                    stock.sector = sector_val
                if industry_val:
                    stock.industry = industry_val
                updated += 1
            seen_stock_ids.add(stock.id)
            existing_link = db.execute(
                select(StockIndex).where(
                    StockIndex.stock_id == stock.id, StockIndex.index_id == idx.id
                )
            ).scalar_one_or_none()
            if existing_link is None:
                db.add(StockIndex(stock_id=stock.id, index_id=idx.id))

        # remove stale memberships for this index
        stale = db.execute(
            delete(StockIndex)
            .where(StockIndex.index_id == idx.id)
            .where(~StockIndex.stock_id.in_(seen_stock_ids))
        )
        removed = stale.rowcount

        result = RefreshResult(
            index_code=index_code,
            status="success",
            stocks_added=added,
            stocks_updated=updated,
            stocks_removed=removed,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Catalog refresh failed for {index_code}")
        result = RefreshResult(index_code=index_code, status="failed", error_message=str(e))
    _finalize_log(log, result)
    return result


def refresh_all(db: Session) -> list[RefreshResult]:
    results: list[RefreshResult] = []
    for code in INDEX_SOURCES:
        results.append(refresh_index(db, code))
    return results
