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


def soft01(x: float, ref: float) -> float:
    """Saturating strength score in [0, 1) that NEVER reaches 1.0.

    Replaces the old `clamp01(x / ref)` for magnitude-style "strength" factors.
    The hard clamp pinned every reading >= ref to exactly 1.0, so a merely-
    sufficient signal and an extreme one scored identically — the main reason
    so many alerts maxed out at confidence 100. This curve keeps a gradient:

        x = ref      -> 0.80   (meets the old "full" bar: strong, not maxed)
        x = 2*ref    -> 0.89
        x = 4*ref    -> 0.94
        x -> inf     -> 1.0    (asymptote, never reached)
        x = ref/2    -> 0.67   (sub-threshold readings fall off faster)

    So two signals that both used to hit 1.0 now separate by their real
    magnitude, and the factor can never on its own force a perfect score."""
    if x <= 0 or ref <= 0:
        return 0.0
    return x / (x + 0.25 * ref)


def trend_maturity_factor(age: int | None) -> float:
    """Backtest-derived favorability of a trend-following entry by trend age
    (bars since the EMA50/EMA200 cross). Forward 21d returns peaked mid-life
    (~120-250 bars) and were weakest for very young (<60) and mature (250+)
    trends, so this factor is non-monotonic by design."""
    if age is None:
        return 0.6
    if age < 60:
        return 0.5
    if age < 120:
        return 0.7
    if age < 250:
        return 1.0
    return 0.35


# Top-of-scale reserve. The raw weighted mean is passed through unchanged up
# to _CONF_KNEE; above it, [_CONF_KNEE, 1.0] is linearly compressed into
# [_CONF_KNEE, _CONF_MAX]. So a "perfect" factor set tops out at _CONF_MAX
# (95) — never 100, which is treated as theoretical, unreachable perfection —
# and strong-but-not-perfect signals spread across the upper band instead of
# all pinning at 100. Leaving the sub-knee region untouched keeps the emission
# floor (settings.signal_min_confidence = 60) unaffected: no signal that used
# to qualify is silently dropped by the reshape.
_CONF_KNEE = 0.72
_CONF_MAX = 0.95


def score(factors: dict[str, float], weights: dict[str, float]) -> int:
    """Weighted mean of [0,1] factors, with the top of the scale reserved
    (see _CONF_KNEE / _CONF_MAX), returned as a 0..100 int."""
    num = sum(clamp01(factors.get(k, 0.0)) * w for k, w in weights.items())
    den = sum(weights.values()) or 1.0
    raw = num / den
    if raw > _CONF_KNEE:
        raw = _CONF_KNEE + (_CONF_MAX - _CONF_KNEE) * (raw - _CONF_KNEE) / (1.0 - _CONF_KNEE)
    return round(100.0 * raw)
