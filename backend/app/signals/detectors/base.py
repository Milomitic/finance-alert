"""Detector contract + SignalMatch + temporal-sequence helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Protocol

import pandas as pd

from app.signals.context import SignalContext
from app.signals.events import Event


# frozen=True makes the fields immutable but NOT hashable — chain/invalidation/
# factors are mutable containers. Don't put SignalMatch in a set or use it as a
# dict key; it is meant to be iterated and serialised to JSON.
@dataclass(frozen=True)
class SignalMatch:
    name: str
    tone: str                       # "bull" | "bear"
    confidence: int                 # 0..100
    signal_date: str                # ISO — date of the chain's last event
    chain: list[dict]               # [{date, label, detail}]
    invalidation: dict | None       # {"level": float, "reason": str}
    factors: dict[str, float] = field(default_factory=dict)
    annotations: dict = field(default_factory=lambda: {"levels": [], "points": []})


class SignalDetector(Protocol):
    name: str
    tone: str
    sources: list[str]
    min_bars: int
    def detect(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext,
    ) -> SignalMatch | None: ...


def _d(iso: str) -> _date:
    return _date.fromisoformat(iso[:10])


def find_after(
    events: list[Event], type_: str, *, after: str, within_days: int,
    direction: str | None = None,
) -> Event | None:
    """First event of `type_` (and optional `direction`) strictly after
    `after` and within `within_days` calendar days. Events assumed
    date-sorted ascending."""
    a = _d(after)
    for e in events:
        if e.type != type_:
            continue
        if direction is not None and e.direction != direction:
            continue
        ed = _d(e.date)
        if ed <= a:
            continue
        if (ed - a).days <= within_days:
            return e
    return None


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score(factors: dict[str, float], weights: dict[str, float]) -> int:
    """Weighted mean of [0,1] factors -> 0..100 int."""
    num = sum(clamp01(factors.get(k, 0.0)) * w for k, w in weights.items())
    den = sum(weights.values()) or 1.0
    return round(100.0 * num / den)
