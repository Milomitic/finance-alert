"""Non-technical event producers (earnings/analyst/insider) + the multi-source
gather_events. Producers are CACHE-ONLY and each wrapped so a failure can never
break the scan. Stubs in this task; real logic in later U3 tasks."""
from __future__ import annotations

import pandas as pd
from loguru import logger

from app.signals.events import Event, extract_events


def produce_earnings_events(db, stock) -> list[Event]:
    from app.services.stock_fundamentals_service import get_fundamentals_cached
    f = get_fundamentals_cached(db, stock.ticker)
    if f is None:
        return []
    out: list[Event] = []
    for ep in (f.earnings or []):
        sp = ep.surprise_pct
        if sp is None or ep.eps_reported is None or not ep.date:
            continue
        direction = "bull" if sp > 0 else "bear"
        # surprise_pct is a percentage (e.g. 15.0 = +15%). Normalise to [0,1]:
        # treat |surprise| of 25% as a "full" magnitude (mag=1.0).
        # For the rare fraction-encoded value (|sp| <= 1.5) scale against 0.25.
        mag = abs(sp) / (25.0 if abs(sp) > 1.5 else 0.25)
        out.append(Event(str(ep.date)[:10], "earnings_surprise", direction,
                         magnitude=float(min(1.0, mag)),
                         payload={"surprise_pct": float(sp), "eps_reported": ep.eps_reported,
                                  "eps_estimate": ep.eps_estimate}, source="earnings"))
    return out


def produce_analyst_events(db, stock) -> list[Event]:
    """Emit analyst_change events (bull=upgrade, bear=downgrade) from cached
    fundamentals.  Cache-only -- never triggers an upstream fetch."""
    from app.services.stock_fundamentals_service import get_fundamentals_cached

    # Grade ordering for inferring direction when `action` is ambiguous.
    _GRADE_RANK: dict[str, int] = {
        "strong sell": 0, "sell": 1, "underperform": 2, "underweight": 2,
        "reduce": 2, "neutral": 3, "market perform": 3, "equal weight": 3,
        "hold": 3, "sector perform": 3, "peer perform": 3,
        "outperform": 4, "overweight": 4, "buy": 5, "strong buy": 6,
    }

    def _infer_direction(action: str, from_grade: str, to_grade: str) -> str | None:
        """Return "bull" / "bear" / None for a single analyst action row."""
        a = (action or "").lower().strip()
        if a in ("up",):
            return "bull"
        if a in ("down",):
            return "bear"
        # Fall back to grade comparison when action is "main" / "reit" / "init" / ""
        fg = _GRADE_RANK.get((from_grade or "").lower().strip())
        tg = _GRADE_RANK.get((to_grade or "").lower().strip())
        if fg is not None and tg is not None:
            if tg > fg:
                return "bull"
            if tg < fg:
                return "bear"
        return None

    f = get_fundamentals_cached(db, stock.ticker)
    if f is None:
        return []
    out: list[Event] = []
    for aa in (f.analyst_actions or []):
        if not getattr(aa, "date", None):
            continue
        direction = _infer_direction(
            getattr(aa, "action", ""),
            getattr(aa, "from_grade", ""),
            getattr(aa, "to_grade", ""),
        )
        if direction is None:
            continue
        out.append(Event(
            str(aa.date)[:10],
            "analyst_change",
            direction,
            magnitude=0.5,
            payload={
                k: v for k, v in {
                    "firm": getattr(aa, "firm", None),
                    "from_grade": getattr(aa, "from_grade", None) or None,
                    "to_grade": getattr(aa, "to_grade", None) or None,
                    "action": getattr(aa, "action", None),
                }.items() if v is not None
            },
            source="analyst",
        ))
    return out


def produce_insider_events(db, stock) -> list[Event]:
    """Emit bull insider_cluster events from cached fundamentals.

    Cache-only -- never triggers an upstream fetch. Bull-only: insider
    BUYS (Purchases) are a meaningful signal; routine SELLS from vesting
    are too noisy to act on.

    Clustering logic: group Purchases by a ~30-day sliding window. A
    window qualifies as a cluster when >=2 DISTINCT insiders bought OR
    total shares bought >= 10,000. Emit one event per cluster dated at
    the latest purchase in the window.
    """
    from app.services.stock_fundamentals_service import (
        _transaction_type,
        get_fundamentals_cached,
    )
    from datetime import date as _date, timedelta

    f = get_fundamentals_cached(db, stock.ticker)
    if f is None:
        return []

    # Collect all Purchase rows that have a date and shares.
    _WINDOW_DAYS = 30
    _MIN_BUYERS = 2
    _MIN_SHARES = 10_000

    purchases = []
    for tx in (f.insiders or []):
        if _transaction_type(tx.transaction) != "Purchase":
            continue
        if not tx.date:
            continue
        try:
            d = _date.fromisoformat(str(tx.date)[:10])
        except ValueError:
            continue
        purchases.append((d, tx.insider, tx.shares or 0))

    if not purchases:
        return []

    # Sort by date ascending then do a forward-looking window sweep.
    purchases.sort(key=lambda x: x[0])

    out: list[Event] = []
    emitted_windows: list[tuple[_date, _date]] = []  # (start, end) of already-emitted clusters

    for i, (d_start, _, _) in enumerate(purchases):
        d_end = d_start + timedelta(days=_WINDOW_DAYS)
        # Gather all purchases inside [d_start, d_end]
        in_window = [(d, ins, sh) for (d, ins, sh) in purchases if d_start <= d <= d_end]
        buyers = {ins for (_, ins, _) in in_window}
        total_shares = sum(sh for (_, _, sh) in in_window)
        latest_date = max(d for (d, _, _) in in_window)

        if len(buyers) < _MIN_BUYERS and total_shares < _MIN_SHARES:
            continue

        # Deduplicate: skip if this cluster is fully covered by a prior emission
        # (its latest_date is within an already-emitted window).
        already_covered = any(ws <= latest_date <= we for (ws, we) in emitted_windows)
        if already_covered:
            continue

        n_buyers = len(buyers)
        # magnitude: max of (buyers / 4) or (shares / floor), clamped [0,1]
        mag = min(1.0, max(n_buyers / 4.0, total_shares / _MIN_SHARES))
        out.append(Event(
            str(latest_date),
            "insider_cluster",
            "bull",
            magnitude=float(mag),
            payload={"n_buyers": n_buyers, "total_shares": int(total_shares)},
            source="insider",
        ))
        emitted_windows.append((d_start, d_end))

    return out


_PRODUCERS = [produce_earnings_events, produce_analyst_events, produce_insider_events]


def gather_events(ohlcv: pd.DataFrame, *, db=None, stock=None) -> list[Event]:
    """Technical events (always) + non-technical events (only when db+stock
    given). Each producer isolated so a failure never breaks the scan."""
    events = list(extract_events(ohlcv))
    if db is not None and stock is not None:
        for prod in _PRODUCERS:
            try:
                events.extend(prod(db, stock))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[signals] producer {prod.__name__} failed: {e}")
    return sorted(events, key=lambda e: e.date)
