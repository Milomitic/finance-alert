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
    return []  # U3-T3


def produce_insider_events(db, stock) -> list[Event]:
    return []  # U3-T4


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
