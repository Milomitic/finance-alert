"""Refresh stock catalog from Wikipedia constituent tables."""
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import CatalogRefreshLog, Index, Stock, StockIndex
from app.services.country_normalizer import canonical_country
from app.services.exchange_codes import canonical_exchange, has_known_suffix
from app.services.industry_normalizer import canonical_industry
from app.services.sector_normalizer import canonical_sector

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
        # 2026-07: Wikipedia SPLIT the constituent list out of the main
        # Nasdaq-100 article into its own page. The old article's table 5 is
        # now a navbox, so the scrape silently returned nothing and the
        # refresh wiped all 101 memberships (see the wipe guards below —
        # they exist because of this). The list page carries the same columns
        # as before, at table 0. Reference footnotes moved [14] → [1].
        "url": "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
        "name": "Nasdaq-100",
        "country": "US",
        "table_index": 0,
        "ticker_col": "Ticker",
        "name_col": "Company",
        "sector_col": "ICB Industry[1]",
        "industry_col": "ICB Subsector[1]",
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
    "FTSEMIB": {
        "url": "https://en.wikipedia.org/wiki/FTSE_MIB",
        "name": "FTSE MIB (Milano)",
        "country": "IT",
        "table_index": 1,
        "ticker_col": "Ticker",
        "name_col": "Company",
        "sector_col": "ICB Sector",
        "industry_col": None,
        "default_exchange": "BIT",
        "currency": "EUR",
    },
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
    # SSE 50 — refresh source REMOVED (2026-05). The index + all
    # 50 .SS constituents were purged from the catalog (see
    # `app/scripts/remove_sse50.py`). Keeping the entry here would
    # cause `catalog_refresh` jobs to re-seed CN stocks the user
    # asked to retire. CSI 300 was already not present.
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
    # CSI 300 also removed from refresh sources (see SSE 50 note above).
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


class CatalogSourceError(RuntimeError):
    """The upstream constituent table was missing/unparseable. Distinct from a
    generic failure so the caller can tell "the source broke" from "our code
    broke" — and so the wipe guards read as a deliberate refusal, not a
    crash."""


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
    # Strip non-breaking space (U+00A0) which Wikipedia sometimes injects
    # between the prefix and the number ("SEHK:\xa05" → "SEHK: 5").
    t = t.replace("\xa0", " ")
    # CSI 300: "SSE: 600519" / "SZSE: 002475"
    if t.startswith("SSE:") or t.startswith("SZSE:"):
        prefix, _, num = t.partition(":")
        num = num.strip()
        if prefix == "SSE":
            return f"{num}.SS", "SSE"
        return f"{num}.SZ", "SZSE"
    # Hang Seng (Wikipedia 2026): "SEHK: 5" → "0005.HK" (4-digit pad)
    if t.startswith("SEHK:"):
        _, _, num = t.partition(":")
        num = num.strip()
        if num.isdigit():
            return f"{int(num):04d}.HK", "HKEX"
    # LSE-default tickers without explicit suffix → append .L for yfinance.
    # Done before canonical_exchange so the suffix-driven mapping kicks in.
    if default_exchange == "LSE" and "." not in t:
        t = f"{t}.L"
    # Mappa centralizzata in `exchange_codes`: per ticker con suffisso noto
    # restituisce sempre il codice canonico (es. ".MI" -> "BIT") sopprimendo
    # il `default_exchange` per-indice. Per ticker senza suffisso noto
    # (US large-caps) restituisce il default invariato.
    return t, canonical_exchange(t, default_exchange)


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


# A refresh may prune constituents, but an index that suddenly reports fewer
# than this share of its known members is a parse regression, not a real
# reshuffle. Deliberately loose: FTSE100's top-50 slice and periodic index
# reviews do move real numbers, just never by half in one run.
_MIN_RETAINED_RATIO = 0.5


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
            sector_raw = (
                str(row.get(src["sector_col"]))
                if src["sector_col"] and not pd.isna(row.get(src["sector_col"]))
                else None
            )
            # Wikipedia tables use a mix of GICS/ICB/FTSE labels — fold them
            # to the canonical taxonomy at ingestion so the catalog stays
            # uniform regardless of source. See `sector_normalizer.py`.
            sector_val = canonical_sector(sector_raw)
            industry_col = src.get("industry_col")
            industry_raw = (
                str(row.get(industry_col))
                if industry_col and not pd.isna(row.get(industry_col))
                else None
            )
            # Same canonicalization story as sector — Wikipedia tables
            # use 200+ sub-industries (Diversified Banks vs Banking
            # Services vs Banks); we collapse to the GICS Industry
            # Group level (~24 buckets). See `industry_normalizer.py`.
            industry_val = canonical_industry(industry_raw)
            # Per ticker con suffisso noto (es. "ENEL.MI") la chiave
            # `(ticker, exchange)` è autoritativa. Per ticker US senza
            # suffisso noto (es. "AAPL") l'exchange è solo il
            # `default_exchange` per-indice e può cambiare fra indici
            # diversi (AAPL: SP500=NASDAQ vs DJI=NYSE). In quel caso
            # cerchiamo per `ticker` soltanto: se la security esiste già
            # la riusiamo invece di duplicarla.
            if has_known_suffix(ticker):
                stmt = select(Stock).where(
                    Stock.ticker == ticker, Stock.exchange == exchange
                )
            else:
                stmt = select(Stock).where(Stock.ticker == ticker)
            stock = db.execute(stmt).scalar_one_or_none()
            if stock is None:
                stock = Stock(
                    ticker=ticker,
                    exchange=exchange,
                    name=name_val,
                    sector=sector_val,
                    industry=industry_val,
                    # INDEX_SOURCES carries ISO-2 literals already, but the
                    # normalizer is the boundary contract: a future source
                    # entry with a full name can't leak into the normalized
                    # column. See `country_normalizer.py`.
                    country=canonical_country(str(src["country"])),
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

        # ── Wipe guards ──────────────────────────────────────────────────
        # On 2026-07-18 this routine deleted all 101 Nasdaq-100 memberships
        # and logged status="success". Wikipedia had changed the page (or
        # served something unparseable), `_fetch_table` returned a frame with
        # no usable tickers, `seen_stock_ids` stayed empty, and the DELETE
        # below happily removed everything not in an empty set. The index then
        # silently vanished from Market Mood and from every breadth number
        # that averages over it.
        #
        # An empty parse is ALWAYS a source failure, never a real index with
        # no members. And a real index does not shed half its constituents
        # overnight — that shape means the page layout moved and we are now
        # reading the wrong table. Both cases must fail loudly and leave the
        # existing membership untouched; the next run repairs it.
        existing_count = db.execute(
            select(func.count())
            .select_from(StockIndex)
            .where(StockIndex.index_id == idx.id)
        ).scalar_one()
        if not seen_stock_ids:
            raise CatalogSourceError(
                f"{index_code}: source returned no usable constituents "
                f"({existing_count} kept) — refusing to wipe the index"
            )
        if existing_count and len(seen_stock_ids) < existing_count * _MIN_RETAINED_RATIO:
            raise CatalogSourceError(
                f"{index_code}: source returned only {len(seen_stock_ids)} of "
                f"{existing_count} known constituents — looks like a parse "
                f"regression, refusing to prune"
            )

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
