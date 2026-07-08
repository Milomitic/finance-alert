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
from app.services import currency_units


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
    # Stocks whose stored history was wiped + refetched at 10y because the
    # incoming bars were on a different price basis (stock split — see
    # PriceBasisMismatch).
    stocks_rebased: int = 0


class PriceBasisMismatch(Exception):
    """The freshly-downloaded bar for a date we already hold differs from the
    stored close by a split-like factor.

    Yahoo back-adjusts its RAW prices for splits (auto_adjust=False only skips
    dividend adjustment), so after a split every historical bar it serves is
    divided by the split ratio — while our stored, never-re-downloaded history
    still carries the old basis. Upserting the incremental frame would splice
    two incompatible price scales into one series and wreck every indicator.
    The overlap-by-one-session fetch (start = min(latest)) guarantees each
    incremental frame re-requests a bar we already hold, so the mismatch is
    detected on the very first post-split fetch and the caller re-downloads
    the stock's full history on the new basis instead.
    """

    def __init__(self, ticker: str, on_date: date, stored: float, incoming: float):
        self.ticker = ticker
        self.on_date = on_date
        self.stored = stored
        self.incoming = incoming
        ratio = stored / incoming if incoming else float("inf")
        super().__init__(
            f"{ticker} {on_date}: stored close {stored} vs downloaded {incoming} "
            f"(ratio {ratio:.3f}) — price basis changed (split?)"
        )


# A same-date close may legitimately differ a little (self-heal of a bar that
# slipped past the market-open guard: an in-flight close is rarely >25% off the
# settled one). Beyond these bounds the difference is a basis change: the
# smallest real split is 3:2 (ratio 1.5 / 0.667), safely outside the band.
_BASIS_RATIO_LOW = 0.75
_BASIS_RATIO_HIGH = 1.33


def _check_price_basis(db: Session, stock: Stock, rows: list[dict]) -> None:
    """Raise PriceBasisMismatch if the earliest incoming bar overlaps a stored
    bar on a different price basis. No-op when there is no overlap (fresh
    backfill of an empty stock) or the stored close matches within the band."""
    if not rows:
        return
    first = rows[0]
    stored = db.execute(
        text("SELECT close FROM ohlcv_daily WHERE stock_id = :sid AND date = :d"),
        {"sid": stock.id, "d": first["date"]},
    ).scalar()
    if stored is None:
        return
    stored_f = float(stored)
    incoming = float(first["close"])
    if incoming <= 0 or stored_f <= 0:
        return
    ratio = stored_f / incoming
    if ratio < _BASIS_RATIO_LOW or ratio > _BASIS_RATIO_HIGH:
        raise PriceBasisMismatch(stock.ticker, first["date"], stored_f, incoming)


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


# SQLite upsert via INSERT ... ON CONFLICT. Module-level so the statement is
# compiled once, and executed as ONE executemany per stock (see _upsert_one_stock).
_UPSERT_STMT = text(
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


def _upsert_one_stock(db: Session, stock: Stock, frame: pd.DataFrame) -> tuple[int, int]:
    """Upsert OHLCV rows for one stock. Returns (inserted, updated).

    For LSE-listed stocks where yfinance reports currency='GBp' (or 'GBX'),
    O/H/L/C are scaled pence->pounds before INSERT so the table is uniformly
    in pounds. The scaling decision + fail-closed contract live in
    `app.services.currency_units` (single owner of the pence/pounds logic).
    """
    inserted = 0
    updated = 0
    # Resolve the pence/pounds scaling decision. Non-LSE tickers skip the
    # metadata HTTP call entirely; a failed lookup on a .L ticker aborts this
    # stock's upsert (fail CLOSED — see currency_units.native_currency_for_scaling).
    native_currency, currency_ok = currency_units.native_currency_for_scaling(stock.ticker)
    if not currency_ok:
        logger.warning(
            f"[ohlcv] currency lookup failed for {stock.ticker} — skipping upsert "
            "this cycle (pence/pounds ambiguity; will retry next fetch)"
        )
        return 0, 0
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

    rows: list[dict] = []
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
        open_v = currency_units.scale_minor_to_major(native_currency, float(row["Open"]))
        high_v = currency_units.scale_minor_to_major(native_currency, float(row["High"]))
        low_v = currency_units.scale_minor_to_major(native_currency, float(row["Low"]))
        close_v = currency_units.scale_minor_to_major(native_currency, float(row["Close"]))
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
        rows.append(
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
    # Split guard: if the earliest incoming bar overlaps a stored bar on a
    # different price basis, abort BEFORE writing anything — the caller
    # re-downloads the full history instead of splicing two scales.
    rows.sort(key=lambda r: r["date"])
    _check_price_basis(db, stock, rows)
    # One executemany per stock instead of one execute per bar: a 10y backfill
    # is ~2520 bars/stock — the per-row roundtrips dominated backfill wall-time.
    if rows:
        db.execute(_UPSERT_STMT, rows)
        # Approximation: count as "inserted" — for analytics not strictly accurate.
        inserted = len(rows)
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
        # Feed the Salute per-source counters on BATCH-wide failures too —
        # previously only per-ticker misses were counted, so the yfinance.ohlcv
        # row froze exactly during real outages. (The breaker-open early-return
        # above stays metrics-silent by design: the breaker has its own card,
        # and counting skipped batches would poison the success rate.)
        from app.services import data_source_metrics
        data_source_metrics.record_failure(
            "yfinance", "ohlcv",
            reason=f"yf.download batch failed: {e}"[:200],
            count=len(stocks),
        )
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
            # Dead-ticker quarantine bookkeeping: consecutive all-empty fetches.
            # Persisted by the caller's per-chunk commit.
            stock.ohlcv_nodata_streak = (stock.ohlcv_nodata_streak or 0) + 1
            stock.ohlcv_last_nodata_at = date.today()
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)
            continue
        try:
            inserted, updated = _upsert_one_stock(db, stock, frame)
            if stock.ohlcv_nodata_streak:
                stock.ohlcv_nodata_streak = 0  # any data → alive again
            result.rows_inserted += inserted
            result.rows_updated += updated
            result.stocks_succeeded += 1
        except PriceBasisMismatch as e:
            logger.warning(f"[ohlcv] price-basis mismatch (split?): {e} — rebasing full history")
            try:
                ins = _rebase_full_history(db, stock)
                result.rows_inserted += ins
                result.stocks_succeeded += 1
                result.stocks_rebased += 1
            except Exception as re_err:  # noqa: BLE001
                logger.exception(f"[ohlcv] rebase failed for {stock.ticker}: {re_err}")
                result.stocks_failed += 1
                result.failed_tickers.append(stock.ticker)
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[ohlcv] upsert failed for {stock.ticker}: {e}")
            result.stocks_failed += 1
            result.failed_tickers.append(stock.ticker)

    if result.stocks_succeeded > 0:
        yfinance_health.record_success()

    # Record per-source metrics for the health dashboard. ONE batch verdict
    # (ok / partial / failed) instead of success-then-failure calls, so the
    # Salute classifier reads a partial batch as "degraded" — not whichever
    # of the two records happened to land last.
    from app.services import data_source_metrics
    data_source_metrics.record_batch(
        "yfinance", "ohlcv",
        succeeded=result.stocks_succeeded,
        failed=result.stocks_failed,
        reason=(
            f"{result.stocks_failed} tickers without data (e.g. {(result.failed_tickers or [])[:3]})"
            if result.stocks_failed > 0 else ""
        ),
    )

    logger.info(
        f"[ohlcv] result: succeeded={result.stocks_succeeded} "
        f"failed={result.stocks_failed} rows={result.rows_inserted}"
    )
    return result


def _rebase_full_history(db: Session, stock: Stock) -> int:
    """Wipe + re-download one stock's full history on the NEW price basis.

    Called when a split is detected: every bar Yahoo now serves is adjusted to
    the post-split scale, so the only consistent repair is a clean 10y refetch.
    Delete and re-insert happen in the CALLER's transaction — if the refetch or
    upsert fails, the caller's rollback restores the old bars (never destroys
    data it can't replace). Returns rows inserted.
    """
    df = _yf_download([stock.ticker], period="10y")
    frame = _extract_ticker_frame(df, stock.ticker)
    if frame is None:
        raise RuntimeError(f"rebase fetch returned no data for {stock.ticker}")
    db.execute(
        text("DELETE FROM ohlcv_daily WHERE stock_id = :sid"), {"sid": stock.id}
    )
    # After the delete there is no stored overlap bar, so the basis check
    # inside _upsert_one_stock is a no-op — no recursion risk.
    inserted, _ = _upsert_one_stock(db, stock, frame)
    logger.info(
        f"[ohlcv] rebased {stock.ticker}: full history re-downloaded "
        f"({inserted} bars on the new price basis)"
    )
    return inserted


# --- Dead-ticker quarantine -------------------------------------------------
# A delisted/renamed symbol never gets bars, so it lands in the backfill group
# of EVERY scan and re-attempts a full 10y download forever — polluting logs
# and the Salute failure counters (e.g. VSCO "possibly delisted"). After
# QUARANTINE_STREAK consecutive all-empty fetches the stock is skipped by the
# scan fetch plans, with a re-probe every REPROBE_DAYS in case the symbol
# comes back (IPO re-listing, yfinance hiccup, exchange migration).
QUARANTINE_STREAK = 3
REPROBE_DAYS = 7


def split_quarantined(
    stocks: list[Stock], today: date | None = None
) -> tuple[list[Stock], list[Stock]]:
    """Partition `stocks` into (fetchable, quarantined) per the rule above."""
    today = today or date.today()
    fetchable: list[Stock] = []
    quarantined: list[Stock] = []
    for s in stocks:
        streak = s.ohlcv_nodata_streak or 0
        last = s.ohlcv_last_nodata_at
        if (
            streak >= QUARANTINE_STREAK
            and last is not None
            and (today - last).days < REPROBE_DAYS
        ):
            quarantined.append(s)
        else:
            fetchable.append(s)
    return fetchable, quarantined


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
