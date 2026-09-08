"""ETF holdings — top components of an ETF/fund via yfinance funds_data.

Powers the stock-detail "Componenti ETF" view: for an ETF, the trend +
day variation of each underlying holding. `funds_data.top_holdings`
exists only for ETFs/funds (a regular equity raises / returns empty), so
we use it as the ETF detector itself.

Cached in fetch_cache (L2, kind="etf_holdings") with a long TTL — holdings
drift slowly. The NON-ETF result (empty list) is cached too, so a regular
stock isn't re-probed against yfinance on every visit.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from loguru import logger
from sqlalchemy.orm import Session

_KIND = "etf_holdings"
_TTL_SECONDS = 7 * 24 * 3600  # 7 days — holdings move slowly
_MAX_HOLDINGS = 25
_CACHE_V = 2  # bump to invalidate pre-underlying-mapping cached rows

# Leveraged/inverse ETF → physical ETF that replicates the SAME index.
# A leveraged ETF holds SWAPS on an index, so yfinance exposes only a few
# direct equity positions — useless for a "components" view. We instead
# substitute the real basket of that index via its physical ETF (full
# holdings on yfinance). Bull and bear map to the SAME underlying: the
# constituents are identical, only direction/leverage differ. Single-stock
# leveraged funds (TSLL/NVDL/CONL) are intentionally omitted — their
# "underlying" is one stock, so the direct-holdings fallback is fine.
_LEVERAGED_UNDERLYING: dict[str, str] = {
    "SOXL": "SOXX", "SOXS": "SOXX",
    "TQQQ": "QQQ", "SQQQ": "QQQ", "QLD": "QQQ",
    "TNA": "IWM", "TZA": "IWM",
    "SPXL": "SPY", "SPXS": "SPY", "UPRO": "SPY", "SPXU": "SPY", "SSO": "SPY", "SDS": "SPY",
    "UDOW": "DIA", "SDOW": "DIA",
    "TECL": "XLK", "TECS": "XLK", "ROM": "XLK",
    "FAS": "XLF", "FAZ": "XLF",
    "LABU": "XBI", "LABD": "XBI",
    "DPST": "KRE",
    "RETL": "XRT",
    "WEBL": "FDN",
    "NUGT": "GDX", "DUST": "GDX",
    "JNUG": "GDXJ", "JDST": "GDXJ",
    "GUSH": "XOP",
    "ERX": "XLE", "ERY": "XLE",
    "DRN": "XLRE",
    "YINN": "FXI", "YANG": "FXI",
    "NAIL": "ITB",
    "DFEN": "ITA",
    "CURE": "XLV",
    "MIDU": "MDY",
    "PILL": "XPH",
}


def underlying_of(ticker: str) -> str | None:
    """The physical ETF whose holdings we substitute for a leveraged
    ETF's swaps; None when `ticker` isn't a mapped leveraged fund."""
    return _LEVERAGED_UNDERLYING.get(ticker.upper())


@dataclass(frozen=True)
class EtfHolding:
    symbol: str
    name: str
    weight: float  # fraction 0..1 of the fund


def get_holdings(db: Session, ticker: str) -> list[EtfHolding]:
    """Top holdings of `ticker` when it's an ETF/fund; [] otherwise.

    L2-cached (including the empty/non-ETF result) so a regular equity is
    probed against yfinance at most once per TTL window.
    """
    from app.services import fetch_cache_store as fcs

    cached = fcs._read_row(db, ticker, _KIND, _TTL_SECONDS)
    if cached is not None:
        try:
            payload = json.loads(cached[0])
            if payload.get("v") == _CACHE_V:  # else stale schema → refetch
                return [EtfHolding(**h) for h in payload.get("holdings", [])]
        except Exception as e:  # noqa: BLE001 — corrupt row → refetch
            logger.debug(f"[etf_holdings] cache parse failed for {ticker}: {e}")

    holdings = _fetch_from_yf(ticker)
    try:
        fcs._upsert(
            db, ticker, _KIND,
            json.dumps({"v": _CACHE_V, "holdings": [asdict(h) for h in holdings]}),
        )
    except Exception as e:  # noqa: BLE001 — caching is best-effort
        logger.debug(f"[etf_holdings] cache write failed for {ticker}: {e}")
    return holdings


def etfs_containing(db: Session, ticker: str) -> list[str]:
    """Which funds carry `ticker`, from the cache `get_holdings` already fills.

    The reverse of `get_holdings`, and it reads ONLY what is cached — a stock
    detail page must never fan out to yfinance across two dozen funds.

    ⚠️ IT CANNOT INVERT THE CACHE LITERALLY. `get_holdings` substitutes a
    physical ETF's basket for a leveraged fund's swaps (`_LEVERAGED_UNDERLYING`,
    see its note above), so SOXL's cached row IS SOXX's basket. Read straight,
    the live cache returns

        NVDA -> SOXL, QQQ, SOXX, SPY, XLK, SOXS

    with the 3x bull and the 3x bear both present. NVDA is inside neither, and
    a page claiming a stock sits in a fund AND in its inverse is worse than one
    that says nothing. Every row is therefore attributed to
    `underlying_of(row) or row`, which collapses the pair back onto SOXX.

    THE CAP IS THE OTHER HALF OF THE HONESTY. `_MAX_HOLDINGS` is 25, so this
    answers "is among the largest positions of", never "is a member of": SPY
    has 503 constituents and a stock ranked 200th correctly gets nothing here.
    Whatever renders this must say which claim it is making, because the
    ABSENCE of a label would otherwise read as "not in that fund".
    """
    from app.models.fetch_cache import FetchCache

    want = (ticker or "").strip().upper()
    if not want:
        return []

    rows = (
        db.query(FetchCache.ticker, FetchCache.payload)
        .filter(FetchCache.kind == _KIND)
        .all()
    )

    found: set[str] = set()
    for row_ticker, payload in rows:
        try:
            data = json.loads(payload)
            if data.get("v") != _CACHE_V:
                continue
            symbols = {
                str(h.get("symbol", "")).strip().upper()
                for h in data.get("holdings", [])
            }
        except Exception as e:  # noqa: BLE001 — one bad row must not 500 a page
            logger.debug(f"[etf_holdings] reverse map skipped {row_ticker}: {e}")
            continue

        if want not in symbols:
            continue
        fund = (underlying_of(row_ticker) or row_ticker).upper()
        if fund != want:  # an ETF listing itself is noise on its own page
            found.add(fund)

    return sorted(found)


def _fetch_from_yf(ticker: str) -> list[EtfHolding]:
    """Pull top_holdings from yfinance. Returns [] for non-funds, on the
    yfinance breaker being open, or any error (never raises)."""
    from app.services import yfinance_health

    if yfinance_health.is_open():
        return []
    # For a mapped leveraged/inverse ETF, fetch the holdings of its
    # physical underlying (the real index basket) instead of the swap-
    # based direct positions.
    fetch_symbol = _LEVERAGED_UNDERLYING.get(ticker.upper(), ticker)
    try:
        import yfinance as yf

        t = yf.Ticker(fetch_symbol)
        fd = t.funds_data
        th = fd.top_holdings  # DataFrame: index=Symbol, cols [Name, Holding Percent]
        if th is None or getattr(th, "empty", True):
            return []
        out: list[EtfHolding] = []
        for sym, row in th.head(_MAX_HOLDINGS).iterrows():
            symbol = str(sym).strip().upper()
            if not symbol or symbol in {"NAN", "NONE"}:
                continue
            name = str(row.get("Name") or "").strip()
            try:
                weight = float(row.get("Holding Percent") or 0.0)
            except (TypeError, ValueError):
                weight = 0.0
            out.append(EtfHolding(symbol=symbol, name=name, weight=weight))
        yfinance_health.record_success()
        return out
    except Exception as e:  # noqa: BLE001 — non-ETF / schema drift / network
        logger.debug(f"[etf_holdings] {ticker}: not a fund or fetch failed: {e}")
        return []
