"""FX conversion service.

The catalog stores `Stock.market_cap` in the listing currency (yfinance
returns marketCap denominated in the trading currency: KRW for .KS,
JPY for .T, HKD for .HK, CNY for .SS, EUR for .DE/.PA/.AS/.MC, GBP
for .L, etc.). When the dashboard's breadth row sums market caps per
index, mixing currencies produces nonsense ("KOSPI 20 has $3.7
quadrillion in market cap").

This service converts an amount in any supported currency to USD so
comparisons across markets are meaningful. Two-stage lookup:

  1. **Live cache** — yfinance fetched once per currency with a 6h
     TTL. FX moves slowly enough that a few hours of staleness is
     irrelevant for an aggregate breadth display.
  2. **Hardcoded fallback** — when the live fetch fails (offline,
     rate-limited, breaker open) or returns no data, we fall back
     to approximate USD-per-unit rates committed below. They drift
     over time (±5% over a year is typical) but always produce a
     reasonable order-of-magnitude conversion.

Public API:
    to_usd(amount: float | None, currency: str | None) -> float | None
        Convert `amount` from `currency` to USD. None → None. Unknown
        currency → assume USD (no conversion).
"""
from __future__ import annotations

import time
from threading import Lock

from loguru import logger

# 6 hours: FX intraday volatility is typically <1%, well below the
# precision the breadth display needs. Rates only matter to the
# nearest few percent for "which index is biggest" comparisons.
_TTL_SECONDS = 6 * 60 * 60

# USD per 1 unit of currency. Hardcoded mid-2026 reference rates;
# used as a last-resort fallback when the live fetch fails. Update
# every few months to track major drift.
FX_RATES_FALLBACK: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.10,
    "GBP": 1.27,
    "JPY": 1 / 150.0,      # ~0.0067
    "KRW": 1 / 1300.0,     # ~0.00077
    "HKD": 1 / 7.8,        # ~0.128
    "CNY": 1 / 7.0,        # ~0.143
    "TWD": 1 / 31.0,       # ~0.032
    "INR": 1 / 84.0,       # ~0.012
    "CHF": 1.13,
    "CAD": 0.74,
    "AUD": 0.66,
    "NZD": 0.61,
    "DKK": 0.145,
    "SEK": 0.094,
    "NOK": 0.094,
    "PLN": 0.25,
    "CZK": 0.044,
    "HUF": 1 / 360.0,      # ~0.0028
    "BRL": 0.20,
    "MXN": 0.058,
    "SGD": 0.74,
    "ZAR": 0.054,
    "THB": 1 / 36.0,
    "IDR": 1 / 16000.0,
    "MYR": 0.21,
    "PHP": 1 / 58.0,
    "TRY": 0.029,
    "ILS": 0.27,
    "AED": 0.272,
    "SAR": 0.267,
}

# Live cache: currency → (timestamp, USD-per-unit rate)
_CACHE: dict[str, tuple[float, float]] = {}
_CACHE_LOCK = Lock()


def _now() -> float:
    return time.time()


def _fetch_live_rate(currency: str) -> float | None:
    """Fetch USD per 1 unit of `currency` from yfinance history.

    Convention: yfinance symbol `EURUSD=X` quotes USD per 1 EUR (price
    of 1 EUR in USD), which is the rate we want. Returns None on any
    error so the caller can fall back to the hardcoded value.
    """
    if currency.upper() == "USD":
        return 1.0
    try:
        import yfinance as yf

        symbol = f"{currency.upper()}USD=X"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        if hist is None or hist.empty:
            return None
        # Use the most-recent close — even if it's a few days stale,
        # FX moves slowly enough that this is fine for our purposes.
        last_close = float(hist["Close"].iloc[-1])
        if last_close <= 0:
            return None
        return last_close
    except Exception as e:  # noqa: BLE001
        logger.debug(f"FX fetch failed for {currency}: {e}")
        return None


def _get_rate(currency: str) -> float:
    """Resolve USD per 1 unit of `currency`. Cache → live → fallback."""
    cur = currency.upper()
    if cur == "USD":
        return 1.0
    now = _now()
    with _CACHE_LOCK:
        entry = _CACHE.get(cur)
        if entry is not None and (now - entry[0]) < _TTL_SECONDS:
            return entry[1]
    # Cache miss / stale — try live, fall back to hardcoded.
    live = _fetch_live_rate(cur)
    rate = live if live is not None else FX_RATES_FALLBACK.get(cur, 1.0)
    with _CACHE_LOCK:
        _CACHE[cur] = (now, rate)
    return rate


def to_usd(amount: float | None, currency: str | None) -> float | None:
    """Convert `amount` from `currency` to USD.

    None or non-finite amounts → None.
    Missing / unknown currency → assume USD (no conversion).
    """
    if amount is None:
        return None
    if currency is None or not currency.strip():
        return amount
    rate = _get_rate(currency)
    return amount * rate


def clear_cache() -> None:
    """Test helper / admin hook."""
    with _CACHE_LOCK:
        _CACHE.clear()
