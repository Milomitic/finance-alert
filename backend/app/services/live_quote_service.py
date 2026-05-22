"""Live quote service — near-real-time price + day stats for one ticker.

Includes a market-hours heuristic per exchange: the price returned during
trading hours is "LIVE", otherwise it's the EOD close. We compute this
server-side from the ticker suffix (`.L` → London, `.HK` → Hong Kong,
bare → US, etc.) + current UTC weekday/time. This is approximate (no
holiday calendar) but accurate enough to drive the UI's LIVE indicator.


Why polling and not WebSockets:
- yfinance has no WebSocket. A real-time provider (Finnhub, Polygon, Alpaca)
  would, but adds an external API key + rate limit per plan.
- For a single-user local-first app, 10-15s polling against `Ticker.fast_info`
  is plenty: the call returns last_price + day_high/low/open + volume in
  ~100-300ms, no rate-limit hit.

Server-side cache (10s TTL) is critical: if the user opens 5 tabs of the same
stock, the frontend polls every 15s × 5 → without cache that's ~33 calls/min
per ticker. With cache TTL 10s, max ~6 calls/min per ticker regardless of tab
count.

Honors the existing yfinance circuit breaker — if it's open we return a
quote with `error` set instead of hitting Yahoo.
"""
import math
import time
from dataclasses import dataclass
from datetime import datetime, time as dtime, timezone
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger


@dataclass
class LiveQuote:
    ticker: str
    price: float | None = None
    prev_close: float | None = None
    change_abs: float | None = None
    change_pct: float | None = None
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: int | None = None
    market_state: str | None = None     # "OPEN" | "CLOSED" | "UNKNOWN"
    currency: str | None = None
    fetched_at: float = 0.0
    error: str | None = None


# Market hours per region, expressed in the exchange's LOCAL timezone +
# its IANA tz name. We convert "now" into that tz (DST-aware via
# `zoneinfo`) and compare against the local open/close — correct
# year-round.
#
# This replaces a previous fixed-UTC table that hardcoded the US window
# as 13:30-21:00 UTC (the UNION of EDT 13:30-20:00 and EST 14:30-21:00).
# That union didn't prevent any real false-CLOSED — on any given day the
# US is in exactly one of EDT/EST — it just flagged the market OPEN for a
# full hour AFTER the real close in summer (and an hour early in winter),
# so a stock stayed "LIVE" ~1h past the actual 16:00 ET bell.
#
# Tuple is (iana_tz_name, (open_h, open_m), (close_h, close_m)) — local.
_MARKET_HOURS_LOCAL: dict[str, tuple[str, tuple[int, int], tuple[int, int]]] = {
    "US": ("America/New_York", (9, 30), (16, 0)),    # NYSE / Nasdaq
    "UK": ("Europe/London",    (8, 0), (16, 30)),    # LSE (.L)
    "EU": ("Europe/Berlin",    (9, 0), (17, 30)),    # Xetra / EuroNext (.MI/.DE/...)
    "HK": ("Asia/Hong_Kong",   (9, 30), (16, 0)),    # HKEX (.HK), lunch break ignored
    "CN": ("Asia/Shanghai",    (9, 30), (15, 0)),    # SSE/SZSE (.SS/.SZ), lunch ignored
}

# ZoneInfo objects are cheap but not free to construct; cache per name.
_TZ_CACHE: dict[str, ZoneInfo] = {}


def _tz(name: str) -> ZoneInfo:
    tz = _TZ_CACHE.get(name)
    if tz is None:
        tz = _TZ_CACHE[name] = ZoneInfo(name)
    return tz


def _exchange_region(ticker: str) -> str:
    """Map a ticker to one of the regions in _MARKET_HOURS_UTC."""
    suffix = ticker.split(".")[-1].upper() if "." in ticker else ""
    if suffix == "L":
        return "UK"
    if suffix in ("MI", "DE", "PA", "AS", "MC", "SW", "BR", "HE", "CO", "IR"):
        return "EU"
    if suffix == "HK":
        return "HK"
    if suffix in ("SS", "SZ"):
        return "CN"
    return "US"


def _is_market_open(ticker: str, now_utc: datetime | None = None) -> bool:
    """True iff the exchange of `ticker` is currently in regular trading hours.
    No holiday calendar — only weekday + time-of-day check, but DST-aware:
    we convert `now` into the exchange's local timezone and compare against
    its local open/close, so the LIVE flag flips exactly at the local bell
    year-round (no summer/winter 1-hour drift)."""
    now = now_utc or datetime.now(timezone.utc)
    region = _exchange_region(ticker)
    tzname, (oh, om), (ch, cm) = _MARKET_HOURS_LOCAL[region]
    local = now.astimezone(_tz(tzname))
    if local.weekday() >= 5:   # Sat/Sun in the exchange's local time
        return False
    cur = local.time()
    return dtime(oh, om) <= cur <= dtime(ch, cm)


# US pre-market session: 4:00–9:30 ET (local). Pre/post-market data is
# reliable on yfinance only for US listings, so this is US-only by design.
_US_PREMARKET_START_LOCAL = dtime(4, 0)


def _is_premarket(ticker: str, now_utc: datetime | None = None) -> bool:
    """True iff `ticker` is a US listing currently in the pre-market
    window (04:00 ET → regular open). Used to swap the displayed day-change
    for the live pre-market move vs the prior session close. DST-aware via
    the exchange-local conversion (same as `_is_market_open`)."""
    if _exchange_region(ticker) != "US":
        return False
    now = now_utc or datetime.now(timezone.utc)
    tzname, (oh, om), _close = _MARKET_HOURS_LOCAL["US"]
    local = now.astimezone(_tz(tzname))
    if local.weekday() >= 5:
        return False
    return _US_PREMARKET_START_LOCAL <= local.time() < dtime(oh, om)


# A pre-market price within this fraction of the prior close is treated
# as "no real pre-market trade yet" (yfinance returns the stale prior
# close as lastPrice when nothing has traded), so we fall back to the
# EOD close-to-close change rather than report a misleading ~0%.
_PREMARKET_EPS = 0.0005  # 0.05%


_CACHE: dict[str, LiveQuote] = {}
_CACHE_LOCK = Lock()
_TTL_SECONDS = 10.0


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _safe_int(v: Any) -> int | None:
    f = _safe_float(v)
    return int(f) if f is not None else None


def _scale_pence_to_pounds(currency: str | None, value: float | None) -> float | None:
    """LSE quotes come back as pence + currency='GBp'. Apply same /100 fix
    as market_cap_service so HSBA.L doesn't show £1359 when it's £13.59."""
    if value is None:
        return None
    if currency in ("GBp", "GBX"):
        return value / 100.0
    return value


def _eod_pair_from_ohlcv(ticker: str) -> tuple[float, float] | None:
    """Return (most_recent_close, prior_close) from our OHLCV daily bars.

    Used when the market is CLOSED: the displayed price + prev_close
    should both be the actual EOD close-to-close pair, not yfinance's
    fast_info `lastPrice` + `previousClose`. yfinance during off-hours
    returns post-market drift quotes for `lastPrice` (a trade that
    happened after the close), which is misleading under the UI label
    "ULTIMA CHIUSURA" — the user expects to see the actual closing
    price, and the day-over-day variation should reflect the close-to-
    close move (the move the market actually delivered today), not the
    extra few basis points of after-hours noise.

    Concrete case that motivated this: MU on 2026-05-09 (Saturday).
    Bars: 5/8 close=$743.82, 5/7 close=$646.63 → real D/D move
    +15.03%. yfinance returned lastPrice=$746.81 (post-market) +
    previousClose=$743.82 → reported variation +0.40%, hiding the
    real move from the user.

    Returns None if the stock isn't in our catalog or we have fewer
    than 2 bars (in which case the caller falls back to the yfinance
    pair + the existing `_override_prev_close_from_ohlcv` heuristic).
    """
    try:
        from app.core.db import SessionLocal
        from app.models import OhlcvDaily, Stock
        from sqlalchemy import desc, select

        with SessionLocal() as db:
            stock = db.execute(
                select(Stock).where(Stock.ticker == ticker).limit(1)
            ).scalars().first()
            if stock is None:
                return None
            bars = db.execute(
                select(OhlcvDaily)
                .where(OhlcvDaily.stock_id == stock.id)
                .order_by(desc(OhlcvDaily.date))
                .limit(2)
            ).scalars().all()
            if len(bars) < 2:
                return None
            return float(bars[0].close), float(bars[1].close)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[live_quote] _eod_pair_from_ohlcv failed for {ticker}: {e}")
        return None


def _override_prev_close_from_ohlcv(ticker: str, live_price: float | None) -> float | None:
    """Compute the correct day-over-day reference close from our OHLCV
    table, overriding yfinance's `previousClose` when it disagrees.

    Why this exists: yfinance's `fast_info["previousClose"]` is sometimes
    wrong, especially after a sharp move or near market open/close —
    observed case for ARM 2026-05-08 returned `previousClose=222.12`
    when the actual prior trading day's close was 237.30 (a -10.11%
    move misread as -3.97%). Our daily OHLCV scan stores the truth;
    rely on it.

    Logic (revised May 2026 after the SOXS bug — user reported
    prev_close=$9.56 when the actual prior-session close was $8.20):

    yfinance's intraday `history()` call sometimes returns a bar dated
    TODAY with `close=<current intraday price>`. When `fetch_and_upsert`
    persists that row, the OhlcvDaily table ends up with a "today" bar
    whose close is an intraday snapshot, NOT a session close. If we
    treated that as "prev_close", we'd report a wildly wrong day-over-
    day move (SOXS: real prev=$8.20, intraday-stored "close"=$9.56 →
    misreported change=−2.7% when reality was +13.4%).

    The fix is to recognise when bars[0] is TODAY's still-open snapshot:
    if `bars[0].date == today (server UTC)` and live_price differs
    meaningfully from `bars[0].close` (>0.5% delta), then bars[0] is an
    intraday snapshot — skip it and use `bars[1].close` as the proper
    prev_close. Caveat: server-UTC-date is an approximation of
    "today in the market's tz"; for the major listings (US, EU, UK)
    the UTC date is within a few hours of the local market date for
    most of the trading session, which is enough for this heuristic.

    Returns None when we can't infer (no Stock row, no bars, only one
    bar, or live_price unknown). Caller falls back to yfinance's value.
    """
    if live_price is None:
        return None
    try:
        from datetime import UTC as _UTC, date as _date, datetime as _dt
        from app.core.db import SessionLocal
        from app.models import OhlcvDaily, Stock
        from sqlalchemy import desc, select

        with SessionLocal() as db:
            stock = db.execute(
                select(Stock).where(Stock.ticker == ticker).limit(1)
            ).scalars().first()
            if stock is None:
                return None
            bars = db.execute(
                select(OhlcvDaily)
                .where(OhlcvDaily.stock_id == stock.id)
                .order_by(desc(OhlcvDaily.date))
                .limit(3)
            ).scalars().all()
            if len(bars) < 2:
                return None
            most_recent_close = float(bars[0].close)
            prior_close = float(bars[1].close)

            today_utc: _date = _dt.now(_UTC).date()
            # Heuristic: if the most-recent bar is dated today AND the
            # live price disagrees materially with its stored close,
            # the bar is an intraday snapshot. Use the prior bar's
            # close as the legitimate prev_close. Threshold: >0.5%
            # delta. Below that we accept the stored close as the
            # session value (markets routinely close within tenths of
            # their last intraday tick, especially during quiet
            # sessions, so a tighter threshold would over-correct).
            if bars[0].date >= today_utc:
                delta_pct = abs(live_price - most_recent_close) / max(
                    abs(most_recent_close), 1e-6
                )
                if delta_pct > 0.005:
                    return prior_close
                # bars[0] is today AND live ≈ stored → looks like a
                # quiet day or post-close write; either way bars[1]
                # is the true prev-session close.
                return prior_close

            # bars[0].date < today: that bar IS a finalised session
            # close. Use the existing "close-of-day vs intraday"
            # disambiguation against the live price.
            if abs(live_price - most_recent_close) < 0.01:
                return prior_close
            return most_recent_close
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[live_quote] _override_prev_close failed for {ticker}: {e}")
        return None


def _eod_fallback_quote(ticker: str) -> LiveQuote:
    """Popola un LiveQuote dall'ultima OhlcvDaily disponibile. Usato quando
    il breaker yfinance è aperto: EOD-stale-but-correct beats blank '—'.

    Returns LiveQuote with error="not_found" if the ticker isn't in the DB,
    error="no_ohlcv" if there are no OHLCV bars, otherwise a fully-populated
    LiveQuote with market_state="CLOSED" and fetched_at=now."""
    from sqlalchemy import select, desc
    from app.core.db import SessionLocal
    from app.models import OhlcvDaily, Stock

    with SessionLocal() as db:
        # .limit(1).scalars().first() tolerates legacy duplicate ticker rows
        # (see CLAUDE.md). All duplicates are equivalent for this read.
        stock = db.execute(
            select(Stock).where(Stock.ticker == ticker).limit(1)
        ).scalars().first()
        if stock is None:
            return LiveQuote(ticker=ticker, error="not_found")
        bars = db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock.id)
            .order_by(desc(OhlcvDaily.date))
            .limit(2)
        ).scalars().all()
        if not bars:
            return LiveQuote(ticker=ticker, error="no_ohlcv")
        last = bars[0]
        prev = bars[1] if len(bars) > 1 else None
        price = float(last.close) if last.close is not None else None
        prev_close = float(prev.close) if (prev and prev.close is not None) else None
        change_abs = None
        change_pct = None
        if price is not None and prev_close not in (None, 0):
            change_abs = price - prev_close
            change_pct = change_abs / prev_close * 100.0
        return LiveQuote(
            ticker=ticker,
            price=price,
            prev_close=prev_close,
            change_abs=change_abs,
            change_pct=change_pct,
            day_open=float(last.open) if last.open is not None else None,
            day_high=float(last.high) if last.high is not None else None,
            day_low=float(last.low) if last.low is not None else None,
            volume=int(last.volume) if last.volume is not None else None,
            market_state="CLOSED",
            fetched_at=time.time(),
            error=None,
        )


def _fetch_fresh(ticker: str) -> LiveQuote:
    """Hit yfinance fast_info for one ticker. Wrapped for monkeypatching."""
    from app.services import yfinance_health
    import yfinance as yf

    if yfinance_health.is_open():
        return _eod_fallback_quote(ticker)

    quote = LiveQuote(ticker=ticker, fetched_at=time.time())

    try:
        t = yf.Ticker(ticker)
        fi: Any = t.fast_info
        # last_price / lastPrice — key spelling differs across versions
        last = _safe_float(fi.get("lastPrice")) if hasattr(fi, "get") else None
        if last is None:
            last = _safe_float(fi.get("last_price")) if hasattr(fi, "get") else None
        prev = _safe_float(fi.get("previousClose"))
        currency = None
        try:
            currency = fi.get("currency")
        except Exception:  # noqa: BLE001
            currency = None

        # Apply pence→pounds for LSE (.L tickers come back as GBp)
        last = _scale_pence_to_pounds(currency, last)
        prev = _scale_pence_to_pounds(currency, prev)
        day_open = _scale_pence_to_pounds(currency, _safe_float(fi.get("open")))
        day_high = _scale_pence_to_pounds(currency, _safe_float(fi.get("dayHigh")))
        day_low = _scale_pence_to_pounds(currency, _safe_float(fi.get("dayLow")))

        # When the market is CLOSED the price under "ULTIMA CHIUSURA"
        # MUST be the actual EOD close (not a post-market drift quote
        # from fast_info.lastPrice), and the variation MUST be the true
        # day-over-day close-to-close move. Source both from OHLCV when
        # we have at least 2 bars. See `_eod_pair_from_ohlcv` for the
        # full rationale + concrete MU case study.
        # When the market is OPEN we keep the existing behavior: live
        # yfinance lastPrice + DB-derived prev_close (which fixes the
        # "yfinance returned wrong previousClose during sharp moves"
        # case observed for ARM on 2026-05-08 → see
        # `_override_prev_close_from_ohlcv` docstring).
        market_open = _is_market_open(ticker)
        last_eff: float | None = last
        state = "OPEN" if market_open else "CLOSED"
        if market_open:
            prev_overridden = _override_prev_close_from_ohlcv(ticker, last_eff)
            prev_effective = prev_overridden if prev_overridden is not None else prev
        else:
            # Market CLOSED. During the US pre-market window, if yfinance
            # has a live pre-market quote, show that move vs yesterday's
            # close INSTEAD of the previous day's close-to-close change —
            # that's the variation the user cares about pre-open.
            #
            # Use yfinance's OWN pair (lastPrice + previousClose) for the
            # pre-market change, NOT the OHLCV prior close. Two reasons:
            #  1. Same-source consistency — mixing a yfinance pre-market
            #     price with an OHLCV close skews the ratio (different
            #     adjustment basis / timestamp).
            #  2. Our daily bar for "yesterday" can be a stale intraday
            #     snapshot (observed: NVDA OHLCV 2026-05-21=219.51 while
            #     the real settled close was 220.12); yfinance's
            #     previousClose is the official prior-session close and is
            #     reliable pre-open (the `_override` machinery exists for
            #     the DIFFERENT problem of wrong previousClose during
            #     sharp INTRADAY moves, which doesn't apply pre-market).
            # Guard: if lastPrice ≈ previousClose (no real pre-market
            # trade yet, yfinance echoes the prior close), fall back to
            # the EOD close-to-close rather than report a misleading ~0%.
            if (
                _is_premarket(ticker)
                and last is not None and prev is not None and prev > 0
                and abs(last - prev) / prev > _PREMARKET_EPS
            ):
                last_eff = last
                prev_effective = prev
                state = "PRE"
            else:
                eod = _eod_pair_from_ohlcv(ticker)
                if eod is not None:
                    last_eff, prev_effective = eod
                else:
                    prev_overridden = _override_prev_close_from_ohlcv(ticker, last_eff)
                    prev_effective = prev_overridden if prev_overridden is not None else prev

        change_abs = (last_eff - prev_effective) if (last_eff is not None and prev_effective is not None) else None
        change_pct = ((change_abs / prev_effective * 100.0) if (change_abs is not None and prev_effective) else None)

        quote.price = last_eff
        quote.prev_close = prev_effective
        quote.change_abs = change_abs
        quote.change_pct = change_pct
        quote.day_open = day_open
        quote.day_high = day_high
        quote.day_low = day_low
        quote.volume = _safe_int(fi.get("lastVolume"))
        # Market state computed locally from ticker suffix + UTC time
        # (yfinance fast_info doesn't expose it; t.info is rate-limited).
        # "OPEN" during regular hours, "PRE" when a live US pre-market
        # quote is driving change_pct, "CLOSED" otherwise. The frontend
        # renders the LIVE badge on "OPEN".
        quote.market_state = state
        quote.currency = "GBP" if currency in ("GBp", "GBX") else currency

        if last is not None:
            yfinance_health.record_success()
        elif yfinance_health.is_rate_limit_error(Exception("empty fast_info")):
            # Defensive: shouldn't reach here normally
            yfinance_health.record_failure("live_quote: empty payload")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[live_quote] {ticker}: {e}")
        quote.error = str(e)
        if yfinance_health.is_rate_limit_error(e):
            yfinance_health.record_failure(f"live_quote {ticker}: {e}")

    # Per-source metrics
    from app.services import data_source_metrics
    if quote.price is not None and quote.error is None:
        data_source_metrics.record_success("yfinance", "live_quote")
    else:
        data_source_metrics.record_failure(
            "yfinance", "live_quote",
            reason=quote.error or "empty payload",
        )

    return quote


def get_quote(ticker: str, *, force_refresh: bool = False) -> LiveQuote:
    """Cached single-ticker quote (TTL 10s). Force-refresh bypasses cache."""
    now = time.time()
    if not force_refresh:
        with _CACHE_LOCK:
            cached = _CACHE.get(ticker)
            if cached is not None and (now - cached.fetched_at) < _TTL_SECONDS:
                return cached
    fresh = _fetch_fresh(ticker)
    with _CACHE_LOCK:
        _CACHE[ticker] = fresh
    return fresh


def get_quotes_batch(tickers: list[str]) -> dict[str, LiveQuote]:
    """Fetch multiple quotes CONCURRENTLY. Cache hits return instantly;
    only cache-miss tickers hit yfinance. Returns {ticker: LiveQuote}.

    Parallelised (May 2026): `fast_info` is a per-Ticker HTTP call, so
    a sequential loop over 50 names on a full cache miss took ~5s —
    too slow for the dashboard's 15s live-poll, and it capped how wide
    the top-movers candidate pool could be (only the ~handful of
    displayed names got polled, so intraday movers outside the EOD set
    never surfaced). A bounded thread pool (I/O-bound work) turns that
    into ~1s. Worker count kept small so concurrent Yahoo load stays
    within tolerance; the yfinance circuit breaker is the backstop.

    No batched yfinance call exists (fast_info is per-Ticker); Stooq
    only exposes EOD, not live, so there's no live fallback when the
    breaker opens — entries with `error` set tell the frontend to
    render a stale state.
    """
    out: dict[str, LiveQuote] = {}
    if not tickers:
        return out
    from concurrent.futures import ThreadPoolExecutor
    # 8 workers: enough to collapse a 50-name batch to ~1s without
    # hammering Yahoo with 50 simultaneous connections.
    workers = min(8, len(tickers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for t, q in zip(tickers, ex.map(get_quote, tickers)):
            out[t] = q
    return out


def clear_cache() -> None:
    """For tests."""
    with _CACHE_LOCK:
        _CACHE.clear()
