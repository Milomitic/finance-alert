"""Mini-chart history for the dashboard live-assets panel.

Returns ~63 trailing daily closes (one trading quarter) per yfinance
symbol so the frontend can render an inline sparkline next to each
row.

Why a separate service from `live_quote_service`
------------------------------------------------
- Different TTL: live quotes are 10s; sparklines change once per
  trading day so 15min is plenty (and keeps yfinance load low).
- Different fetch shape: quotes use `Ticker.fast_info`; sparklines
  need `yfinance.download(...)` with a date range. Batching all 13
  symbols in one call costs ~700ms once per 15min vs. 13 sequential
  calls.
- Different failure mode: a sparkline that's a few hours stale is
  fine; a quote that's 15min stale is wrong.

Why 3mo daily
-------------
- 3mo at daily resolution gives ~63 closes — short enough that each
  day's bar is visually resolvable on a ~180px-wide sparkline (~3px
  per day, vs. the 1y version where 252 days compressed into the
  same width gave ~0.7px per day, smearing the daily variation the
  user actually wants to see).
- 63 floats × 13 symbols ≈ 800 floats ≈ ~8 KB JSON, lighter still
  than the 1y version.
- We trade off the annual context (drawdowns, regime shifts a year
  back) for richer recent-trend legibility — that's the right call
  for a "what's this asset doing lately" dashboard panel.

Falls back gracefully: if the batch download fails or a symbol has
no data, the per-symbol entry is `None`. The frontend then just
omits the sparkline for that row.
"""
from __future__ import annotations

import time
from threading import Lock

from loguru import logger

# 15-minute TTL — daily closes only refresh once per trading day, so
# even an hour-stale sparkline is visually identical. The 15min cap is
# really just to absorb intraday changes (today's partial close ticks
# up the last point as the day progresses).
_TTL_SECONDS = 15 * 60

# Lazy yfinance import — keeps `app` startup snappy and lets tests
# monkeypatch the function before yfinance triggers any network call.
_CACHE: dict[str, tuple[float, list[float] | None]] = {}
_CACHE_LOCK = Lock()


def _now() -> float:
    return time.time()


def _fetch_batch(symbols: list[str]) -> dict[str, list[float] | None]:
    """One batched download. Returns symbol → list[float] | None.

    Patchable in tests via `monkeypatch.setattr(live_sparkline_service,
    '_fetch_batch', lambda syms: {...})`.
    """
    import yfinance as yf  # local import for fast app boot

    out: dict[str, list[float] | None] = {s: None for s in symbols}
    if not symbols:
        return out
    try:
        # `period="3mo"` gives ~63 trading days; `interval="1d"` keeps
        # daily granularity so each bar is visible at typical row
        # widths. `group_by="ticker"` returns a multi-index DataFrame
        # even for a single symbol so the access pattern is uniform.
        df = yf.download(
            tickers=" ".join(symbols),
            period="3mo",
            interval="1d",
            progress=False,
            group_by="ticker",
            threads=True,
            auto_adjust=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Sparkline batch download failed: {e}")
        return out

    if df is None or df.empty:
        return out

    for sym in symbols:
        try:
            # When yfinance gets a SINGLE symbol the columns aren't
            # nested — handle both shapes.
            if len(symbols) == 1:
                series = df["Close"]
            else:
                series = df[sym]["Close"] if sym in df.columns.get_level_values(0) else None
            if series is None:
                continue
            closes = [float(v) for v in series.dropna().tolist()]
            out[sym] = closes if closes else None
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Sparkline parse failed for {sym}: {e}")
            out[sym] = None
    return out


def get_sparklines(symbols: list[str]) -> dict[str, list[float] | None]:
    """Return per-symbol close arrays. Cached entries that haven't expired
    are returned unchanged; only stale/missing symbols hit yfinance."""
    now = _now()
    out: dict[str, list[float] | None] = {}
    to_fetch: list[str] = []
    with _CACHE_LOCK:
        for s in symbols:
            entry = _CACHE.get(s)
            if entry is not None and (now - entry[0]) < _TTL_SECONDS:
                out[s] = entry[1]
            else:
                to_fetch.append(s)
    if to_fetch:
        fetched = _fetch_batch(to_fetch)
        with _CACHE_LOCK:
            for s, val in fetched.items():
                _CACHE[s] = (now, val)
                out[s] = val
    return out


def clear_cache() -> None:
    """Test helper / admin hook."""
    with _CACHE_LOCK:
        _CACHE.clear()
