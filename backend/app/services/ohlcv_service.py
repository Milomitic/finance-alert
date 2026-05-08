"""Fetch OHLCV from yfinance and upsert into ohlcv_daily."""
from dataclasses import dataclass
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock


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
    for ts, row in frame.iterrows():
        d = ts.date() if isinstance(ts, pd.Timestamp) else ts
        # Scale pence->pounds for LSE before INSERT. Pass-through for everything else.
        open_v = _normalize_minor_unit_value(native_currency, float(row["Open"]))
        high_v = _normalize_minor_unit_value(native_currency, float(row["High"]))
        low_v = _normalize_minor_unit_value(native_currency, float(row["Low"]))
        close_v = _normalize_minor_unit_value(native_currency, float(row["Close"]))
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
    db: Session, stocks: list[Stock], *, period: str = "1mo"
) -> FetchResult:
    """Fetch OHLCV for the given stocks via yfinance and upsert into ohlcv_daily.

    period: yfinance period string ('1mo', '1y', etc.). Use '1y' for first backfill,
            '1mo' for incremental scans.

    Resilience: if the yfinance circuit breaker is OPEN we skip yfinance and
    route the entire batch through the Stooq fallback. If yfinance fails on
    THIS call (rate-limit fingerprint), we trip the breaker and re-route via
    Stooq. Stooq has no batch endpoint, so the fallback is per-ticker.
    """
    from app.services import yfinance_health
    from app.services.stooq_ohlcv_service import upsert_via_stooq

    if not stocks:
        return FetchResult()
    tickers = [s.ticker for s in stocks]

    # Map yfinance period string to a days-back number for Stooq fallback.
    # `10y` and `max` cover the deep-backfill paths added when we extended
    # the chart range to 5Y (see api/alerts.py + scheduler/jobs/scan_alerts.py).
    days_for_period = {
        "1mo": 35, "3mo": 100, "6mo": 200,
        "1y": 380, "2y": 760, "5y": 1900, "10y": 3800, "max": 6000,
    }.get(period, 380)

    if yfinance_health.is_open():
        logger.info(f"[ohlcv] yfinance breaker OPEN — using Stooq fallback for {len(tickers)} tickers")
        sr = upsert_via_stooq(db, stocks, days=days_for_period)
        return FetchResult(
            rows_inserted=sr.rows_inserted,
            stocks_succeeded=sr.stocks_succeeded,
            stocks_failed=sr.stocks_failed,
            failed_tickers=sr.failed_tickers,
        )

    logger.info(f"[ohlcv] fetching {len(tickers)} tickers via yfinance, period={period}")
    try:
        df = _yf_download(tickers, period=period)
    except Exception as e:  # noqa: BLE001
        if yfinance_health.is_rate_limit_error(e):
            yfinance_health.record_failure(f"yf.download: {e}")
            logger.warning(f"[ohlcv] yfinance.download rate-limited → Stooq fallback")
            sr = upsert_via_stooq(db, stocks, days=days_for_period)
            return FetchResult(
                rows_inserted=sr.rows_inserted,
                stocks_succeeded=sr.stocks_succeeded,
                stocks_failed=sr.stocks_failed,
                failed_tickers=sr.failed_tickers,
            )
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
