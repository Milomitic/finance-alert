"""Non-technical event producers (earnings/analyst/insider) + the multi-source
gather_events. Producers are CACHE-ONLY and each wrapped so a failure can never
break the scan. Stubs in this task; real logic in later U3 tasks."""
from __future__ import annotations

import pandas as pd
from loguru import logger

from app.signals.events import Event, extract_events


def produce_earnings_events(db, stock) -> list[Event]:
    return []  # U3-T2


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
