"""Fetch OHLCV from yfinance and upsert into ohlcv_daily."""
import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock


def _is_bad_price(v: float | None) -> bool:
    # yfinance occasionally returns bars (notably for LSE / some EU tickers
    # in narrow time windows) where Close is the real closing print but
    # Open/High/Low are all 0. Storing those produces a fake candle that
    # plunges from price→0→price on every chart. Reject the row entirely.
    if v is None:
        return True
    try:
        f = float(v)
    except (TypeError, ValueError):
        return True
    return math.isnan(f) or math.isinf(f) or f <= 0


@dataclass
class FetchResult:
    rows_inserted: int = 0
    rows_updated: int = 0
    stocks_succeeded: int = 0
    stocks_failed: int = 0
    failed_tickers: list[str] | None = None


def _normalize_minor_unit_value(currency: str | None, value: float | None) -> float | None:
    """Scale pence to pounds for LSE quotes.

    yfinance returns LSE-listed stocks (.L) with currency='GBp' or 'GBX'
    and prices in pence. ohlcv_daily must store pounds so that downstream
    consumers (chart, indicators, prev_close override, score, alerts)
    are unit-consistent with live_quote_service.

    Mirror of live_quote_service._scale_pence_to_pounds. Documented in
    docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md
    Phase 2.

    Returns None unchanged. USD / EUR / GBP (already-pounds -- e.g. CPG.L,
    IHG.L, MTLN.L on the LSE) pass through.
    """
    if value is None:
        return None
    if currency in ("GBp", "GBX"):
        return value / 100.0
    return value


def _get_yfinance_native_currency(ticker: str) -> str | None:
    """Return yfinance's raw `fast_info["currency"]` for a ticker, or None
    on any error (rate-limit, network, ticker not found, etc.).

    Why query yfinance instead of `Stock.currency`: the catalog normalizes
    Stock.currency uniformly to 'GBP' for both GBp-priced and GBP-priced
    LSE stocks. Only the raw yfinance currency keeps the distinction we
    need for the pence/pounds scaling decision.

    Wrapped in a try/except so any failure returns None and the caller
    can fail-safe (don't scale -- pass-through). Better unscaled than
    incorrectly scaled.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fi: Any = t.fast_info
        return fi.get("currency")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ohlcv] _get_yfinance_native_currency({ticker}): {e}")
        return None


def _yf_download(tickers: list[str], **kwargs: Any) -> pd.DataFrame:
    """Wrap yfinance.download for monkeypatching in tests."""
    import yfinance as yf

    return yf.download(
        tickers=tickers,
        group_by="ticker",
        progress=False,
        auto_adjust=False,
        **kwargs,
    )


def _extract_ticker_frame(df: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Pull the per-ticker subframe out of yfinance's multi-index column response.

    Returns None if the ticker has no data.
    """
    if df is None or df.empty:
        return None
    # yfinance returns a multi-index DataFrame when multiple tickers are requested.
    if isinstance(df.columns, pd.MultiIndex):
        if ticker not in df.columns.get_level_values(0):
            return None
        frame = df[ticker].dropna(how="all")
    else:
        # Single-ticker response: columns are flat
        frame = df.dropna(how="all")
    if frame.empty:
        return None
    return frame


def _upsert_one_stock(db: Session, stock: Stock, frame: pd.DataFrame) -> tuple[int, int]:
    """Upsert OHLCV rows for one stock. Returns (inserted, updated).

    For LSE-listed stocks where yfinance reports currency='GBp' (or 'GBX'),
    O/H/L/C are scaled pence->pounds before INSERT so the table is uniformly
    in pounds. See docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md.

    The currency check uses yfinance's raw `fast_info["currency"]` rather
    than `Stock.currency` because the catalog normalizes Stock.currency
    to 'GBP' uniformly for both GBp-priced and GBP-priced LSE stocks.
    """
    inserted = 0
    updated = 0
    # Look up yfinance's native currency once per stock. Fails to None on
    # any error -> caller passes through (no scaling, fail-safe).
    native_currency = _get_yfinance_native_currency(stock.ticker)
    # The latest date in the frame. yfinance routinely returns the most
    # recent bar with O/H/L populated but Close=NaN — the session hasn't
    # "settled" yet at the data provider (very common for Asian markets
    # like TSE `.T` when we fetch in European evening hours = next-day
    # JST). That specific shape is EXPECTED, not data corruption: we
    # still skip the row (a NaN close would wreck the chart) but log it
    # at DEBUG so it doesn't flood the WARNING-level platform-health
    # stream. A corrupt bar anywhere ELSE in the history, or one with
    # multiple bad fields, stays a WARNING because it's actionable.
    try:
        _latest_date = max(
            (ts.date() if isinstance(ts, pd.Timestamp) else ts)
            for ts in frame.index
        )
    except (ValueError, TypeError):
        _latest_date = None
    # Skip writing a bar dated TODAY while the market is still open:
    # yfinance returns the in-progress session as a "today" bar whose
    # close is the CURRENT intraday price, not a settled session close.
    # Persisting it pollutes every close-to-close consumer — the EOD
    # movers snapshot reported SOXS/SOXL/OKLO day-changes off an
    # intraday value instead of yesterday's real close. The daily table
    # must hold SETTLED closes only; intraday display is the live-quote
    # service's job. After the close the EOD scan writes the real bar.
    # Computed once (market-open state doesn't change mid-loop).
    _skip_today = False
    try:
        from datetime import UTC as _UTC, datetime as _dt
        from app.services.live_quote_service import _is_market_open
        if _is_market_open(stock.ticker):
            _skip_today = True
            _today_utc = _dt.now(_UTC).date()
    except Exception:  # noqa: BLE001 — never block ingestion on this guard
        _skip_today = False

    for ts, row in frame.iterrows():
        d = ts.date() if isinstance(ts, pd.Timestamp) else ts
        # Intraday "today" bar while market open → skip (see above).
        if _skip_today and d >= _today_utc:
            logger.debug(
                f"[ohlcv] skip today's unsettled bar {stock.ticker} {d} "
                f"(market open — intraday snapshot, not a session close)"
            )
            continue
        # Scale pence->pounds for LSE before INSERT. Pass-through for everything else.
        open_v = _normalize_minor_unit_value(native_currency, float(row["Open"]))
        high_v = _normalize_minor_unit_value(native_currency, float(row["High"]))
        low_v = _normalize_minor_unit_value(native_currency, float(row["Low"]))
        close_v = _normalize_minor_unit_value(native_currency, float(row["Close"]))
        bad_open = _is_bad_price(open_v)
        bad_high = _is_bad_price(high_v)
        bad_low = _is_bad_price(low_v)
        bad_close = _is_bad_price(close_v)
        if bad_open or bad_high or bad_low or bad_close:
            # Expected, benign shape: the LATEST bar, where ONLY the
            # close is bad (O/H/L are valid). This is yfinance's
            # unsettled-last-bar artifact — skip quietly at DEBUG.
            is_unsettled_last_bar = (
                d == _latest_date
                and bad_close
                and not (bad_open or bad_high or bad_low)
            )
            msg = (
                f"[ohlcv] skip corrupt bar {stock.ticker} {d}: "
                f"O={open_v} H={high_v} L={low_v} C={close_v}"
            )
            if is_unsettled_last_bar:
                logger.debug(f"{msg} (last bar, close not settled)")
            else:
                logger.warning(msg)
            continue
        # SQLite upsert via INSERT ... ON CONFLICT
        stmt = text(
            """
            INSERT INTO ohlcv_daily (stock_id, date, open, high, low, close, volume)
            VALUES (:stock_id, :date, :open, :high, :low, :close, :volume)
            ON CONFLICT(stock_id, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume
            """
        )
        db.execute(
            stmt,
            {
                "stock_id": stock.id,
                "date": d,
                "open": open_v,
                "high": high_v,
                "low": low_v,
                "close": close_v,
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            },
        )
        # Approximation: count as "inserted" — for analytics not strictly accurate.
        inserted += 1
    return inserted, updated


def fetch_and_upsert(
    db: Session, stocks: list[Stock], *,
    period: str | None = "1mo",
    start: date | None = None,
) -> FetchResult:
    """Fetch OHLCV for the given stocks via yfinance and upsert into ohlcv_daily.

    Pass EITHER `period` (e.g. "1mo", "10y") OR `start` (a date) — not both.
    `start=` is the smart-incremental path used by the scan loop: pulls only
    the bars from `start` (inclusive) to today. Drastically cheaper than
    `period="1mo"` when most stocks already have a recent bar (e.g. on
    consecutive scans the same day, `start = today - 1` returns ~1 bar
    per stock instead of ~22).

    `period` is kept for the backfill path (period="10y") and any caller
    that doesn't have a per-stock latest-date map handy (e.g. the cron
    job or one-off scripts).

    Resilience: if the yfinance circuit breaker is OPEN we skip the
    download entirely and return an empty result — the scan will retry
    on the next scheduled tick, by which time the breaker should have
    closed. We previously had a Stooq fallback here, but Stooq
    introduced an API-key requirement (May 2026) that broke the CSV
    endpoint, and no free-tier alternative we evaluated (Polygon 5/min,
    Tiingo 1000/day, Finnhub /stock/candle behind paywall) can service
    a batch of ~1100 tickers in reasonable time. Skipping the run is
    cheaper than serving stale/wrong data via a degraded source.
    """
    from app.services import yfinance_health

    if not stocks:
        return FetchResult()
    tickers = [s.ticker for s in stocks]

    if yfinance_health.is_open():
        logger.info(
            f"[ohlcv] yfinance breaker OPEN — skipping batch of {len(tickers)} tickers; "
            "will retry next cycle"
        )
        return FetchResult(stocks_failed=len(stocks), failed_tickers=tickers[:])

    # Build the kwargs for yfinance: prefer `start=` when provided
    # (smart-incremental); otherwise fall back to `period=`.
    yf_kwargs: dict[str, object] = (
        {"start": start.isoformat()} if start is not None else {"period": period or "1mo"}
    )
    label = f"start={start.isoformat()}" if start is not None else f"period={period}"
    logger.info(f"[ohlcv] fetching {len(tickers)} tickers via yfinance, {label}")
    try:
        df = _yf_download(tickers, **yf_kwargs)
    except Exception as e:  # noqa: BLE001
        if yfinance_health.is_rate_limit_error(e):
            yfinance_health.record_failure(f"yf.download: {e}")
            logger.warning(
                "[ohlcv] yfinance.download rate-limited — breaker tripped; "
                "skipping batch (no fallback available)"
            )
            return FetchResult(stocks_failed=len(stocks), failed_tickers=tickers[:])
        logger.error(f"[ohlcv] yfinance.download crashed: {e}")
        return FetchResult(stocks_failed=len(stocks), failed_tickers=tickers[:])

    result = FetchResult(failed_tickers=[])
    for stock in stocks:
        frame = _extract_ticker_frame(df, stock.ticker)
        if frame is None:
            logger.warning(f"[ohlcv] no data for {stock.ticker}")
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)
            continue
        try:
            inserted, updated = _upsert_one_stock(db, stock, frame)
            result.rows_inserted += inserted
            result.rows_updated += updated
            result.stocks_succeeded += 1
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[ohlcv] upsert failed for {stock.ticker}: {e}")
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)

    if result.stocks_succeeded > 0:
        yfinance_health.record_success()

    # Record per-source metrics for the health dashboard
    from app.services import data_source_metrics
    if result.stocks_succeeded > 0:
        data_source_metrics.record_success("yfinance", "ohlcv", count=result.stocks_succeeded)
    if result.stocks_failed > 0:
        data_source_metrics.record_failure(
            "yfinance", "ohlcv",
            reason=f"{result.stocks_failed} tickers without data (e.g. {(result.failed_tickers or [])[:3]})",
            count=result.stocks_failed,
        )

    logger.info(
        f"[ohlcv] result: succeeded={result.stocks_succeeded} "
        f"failed={result.stocks_failed} rows={result.rows_inserted}"
    )
    return result


def latest_ohlcv_date(db: Session, stock_id: int) -> Any | None:
    """Return the most recent date for which we have ohlcv_daily data, or None."""
    row = (
        db.query(OhlcvDaily.date)
        .filter(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date.desc())
        .limit(1)
        .one_or_none()
    )
    return row[0] if row else None


def latest_ohlcv_dates_bulk(
    db: Session, stock_ids: list[int]
) -> dict[int, Any]:
    """Return {stock_id: most_recent_date} for the given stock_ids.

    Bulk variant of `latest_ohlcv_date` — one GROUP BY scan instead of N
    indexed lookups. Stocks with no rows are absent from the result dict
    (the caller should treat that as "needs full backfill").

    Used by the manual-scan endpoint to decide 10y backfill vs 1mo
    incremental for every chunk upfront, replacing the per-chunk loop
    that issued one SELECT per stock × chunk-size.
    """
    if not stock_ids:
        return {}
    from sqlalchemy import func

    rows = (
        db.query(OhlcvDaily.stock_id, func.max(OhlcvDaily.date))
        .filter(OhlcvDaily.stock_id.in_(stock_ids))
        .group_by(OhlcvDaily.stock_id)
        .all()
    )
    return {sid: d for sid, d in rows}
