"""Input loaders for the scoring pipeline: OHLCV series (per-stock and bulk),
90d volatility, and the news-count reader. The bulk loader is the I/O
fast path recompute_all uses to avoid ~1100×2 per-stock SELECTs.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily
from app.services import stock_news_service
from app.services.score_service.common import _is_finite


def _compute_volatility_90d(closes: pd.Series | None) -> float | None:
    """90-day daily-return stdev as a percent (e.g. 2.0 means 2.0%/day)."""
    if closes is None or len(closes) < 60:
        return None
    window = closes.iloc[-90:] if len(closes) >= 90 else closes
    rets = window.pct_change().dropna()
    if rets.empty:
        return None
    std = float(rets.std())
    if not _is_finite(std):
        return None
    return std * 100.0


def _last_30d_news_count(ticker: str) -> int | None:
    """Count of news items from the last 30 days. None on fetch failure."""
    try:
        items = stock_news_service.get_news(ticker, limit=50)
    except Exception:  # noqa: BLE001
        return None
    if not items:
        return 0
    today = datetime.now(UTC).date()
    count = 0
    for n in items:
        pub = n.get("published_at")
        if not pub:
            continue
        try:
            d = datetime.fromisoformat(pub.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if (today - d).days <= 30:
            count += 1
    return count


def _load_closes(db: Session, stock_id: int, limit: int = 260) -> pd.Series | None:
    """Ascending close-price series. None if no bars.

    Per-stock SELECT. Used by the single-stock API path
    (`POST /api/stocks/{ticker}/score/recompute`) where one query is
    fine. The bulk recompute_all path uses _bulk_load_recent_bars
    instead to avoid N×SELECT (1100+ queries) — see that function and
    `compute_score(bars=...)` for the fast path.
    """
    rows = db.execute(
        select(OhlcvDaily.close)
        .where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date.asc())
    ).scalars().all()
    if not rows:
        return None
    if len(rows) > limit:
        rows = rows[-limit:]
    return pd.Series([float(c) for c in rows])


def _load_ohlcv_df(db: Session, stock_id: int, limit: int = 260) -> pd.DataFrame | None:
    """Full OHLC frame for ADX. None if no bars.

    Per-stock SELECT. See `_load_closes` note for why recompute_all
    uses the bulk loader instead.
    """
    rows = db.execute(
        select(OhlcvDaily.high, OhlcvDaily.low, OhlcvDaily.close)
        .where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date.asc())
    ).all()
    if not rows:
        return None
    if len(rows) > limit:
        rows = rows[-limit:]
    return pd.DataFrame(
        {
            "high": [float(r[0]) for r in rows],
            "low": [float(r[1]) for r in rows],
            "close": [float(r[2]) for r in rows],
        }
    )


def _bulk_load_recent_bars(
    db: Session, days_back: int = 400
) -> dict[int, list[tuple[float, float, float]]]:
    """Single SELECT pulling the last `days_back` calendar days of OHLCV
    bars for the entire universe, grouped by stock_id.

    Wins over per-stock SELECT (the path compute_score uses for the
    single-stock API endpoint): replaces ~1100 `_load_closes`/`_load_ohlcv_df`
    round-trips with one bulk-cursor pass. Empirical: bulk SELECT of
    ~280k rows on the warm fingerprint completes in ~80-150ms, versus
    ~6-15ms × 2 SELECT × 1100 stocks = 13-33s of cumulative per-stock
    DB time. ~100× faster on the I/O leg.

    `days_back=400` covers ~260 trading days × at-least-65% coverage for
    indicator computation (SMA200, RSI14, ADX14 all fit in a 260-bar
    window). Stocks with less than `days_back` of history return whatever
    they have; indicators that can't compute return None as before.

    Bars come out ordered ASC by date inside each list (matches the
    semantics of the per-stock loaders so downstream code is identical).

    Returns: {stock_id: [(high, low, close), ...]}. Empty dict when no
    bars match the date filter.
    """
    from datetime import date as _date
    from datetime import timedelta as _td

    cutoff = _date.today() - _td(days=days_back)
    rows = db.execute(
        select(
            OhlcvDaily.stock_id,
            OhlcvDaily.date,
            OhlcvDaily.high,
            OhlcvDaily.low,
            OhlcvDaily.close,
        )
        .where(OhlcvDaily.date >= cutoff)
        .order_by(OhlcvDaily.stock_id.asc(), OhlcvDaily.date.asc())
    ).all()
    out: dict[int, list[tuple[float, float, float]]] = {}
    for stock_id, _d, high, low, close in rows:
        out.setdefault(stock_id, []).append((float(high), float(low), float(close)))
    return out
