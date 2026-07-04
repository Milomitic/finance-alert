"""Single owner of the minor-unit (pence) → major-unit (pounds) normalization.

yfinance quotes LSE-listed stocks (.L) with currency='GBp' or 'GBX' and
prices in PENCE, while every downstream consumer (chart, indicators,
prev_close override, score, alerts, treemap, analyst targets) works in
POUNDS. Unscaled, HSBA.L shows £1359 instead of £13.59 (the "×100 bug")
and its marketCap reads ~£23 trillion instead of ~£233 billion.

This logic used to be quintuplicated — ohlcv_service, live_quote_service,
market_cap_service, timeframe_service and stock_fundamentals_service each
carried a copy documenting itself as a "mirror" of the others. This module
is now the single source of truth; all five import from here so the paths
can never drift apart again. Documented in
docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md.

Other minor-unit currencies (ZAc cents, ILA agorot, etc.) could be added
to MINOR_UNIT_CURRENCIES as needed; only GBp/GBX ever showed up in our
LSE-heavy catalog.
"""
from typing import Any

from loguru import logger

# yfinance's spellings for London pence. 'GBP' (uppercase) is POUNDS — a few
# LSE mainboard names (CPG.L, IHG.L, MTLN.L per audit) quote directly in
# pounds and must NOT be scaled.
MINOR_UNIT_CURRENCIES = ("GBp", "GBX")


def is_minor_unit(currency: str | None) -> bool:
    """True when `currency` is a minor-unit spelling (pence) that needs /100."""
    return currency in MINOR_UNIT_CURRENCIES


def scale_minor_to_major(currency: str | None, value: float | None) -> float | None:
    """Scale a pence value to pounds when `currency` is GBp/GBX.

    Returns None unchanged. USD / EUR / GBP (already-pounds) pass through.
    A None currency also passes through (fail-safe for DISPLAY paths: better
    an unscaled value than an incorrectly scaled one — the INGEST path has
    the stricter fail-closed gate in `native_currency_for_scaling`).
    """
    if value is None:
        return None
    if is_minor_unit(currency):
        return value / 100.0
    return value


def get_native_currency(ticker: str) -> str | None:
    """Return yfinance's raw `fast_info["currency"]` for a ticker, or None
    on any error (rate-limit, network, ticker not found, etc.).

    Why query yfinance instead of `Stock.currency`: the catalog normalizes
    Stock.currency uniformly to 'GBP' for both GBp-priced and GBP-priced
    LSE stocks. Only the raw yfinance currency keeps the distinction we
    need for the pence/pounds scaling decision.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fi: Any = t.fast_info
        return fi.get("currency")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[currency_units] get_native_currency({ticker}): {e}")
        return None


# Successful currency lookups, memoized for the process lifetime — a listing's
# quote currency doesn't change. Failures are NOT cached (retry next fetch).
_CURRENCY_CACHE: dict[str, str] = {}


def native_currency_for_scaling(ticker: str) -> tuple[str | None, bool]:
    """Resolve the native currency for the pence→pounds scaling decision.

    Returns (currency, ok):
    - Non-LSE tickers can never be GBp/GBX → (None, True) with NO network
      call. This kills ~1 metadata HTTP round-trip per stock per fetch for
      ~97% of the universe (fast_info.currency triggers a real request).
    - LSE (.L) tickers: memoized fast_info lookup. On lookup failure we
      FAIL CLOSED → (None, False): the caller must skip the stock this
      cycle. Failing open here stored raw pence (100× too high) over
      previously-correct pounds rows whenever the lookup transiently
      failed for a genuinely GBp-priced stock.
    """
    if not ticker.upper().endswith(".L"):
        return None, True
    cached = _CURRENCY_CACHE.get(ticker)
    if cached is not None:
        return cached, True
    currency = get_native_currency(ticker)
    if currency is None:
        return None, False
    _CURRENCY_CACHE[ticker] = currency
    return currency, True
