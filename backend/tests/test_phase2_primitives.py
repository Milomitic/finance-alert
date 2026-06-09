"""Phase 2 — new event primitives: ema_reject (return-to-EMA + rejection) and
swing_pivot (lower-high / higher-low continuation structure)."""
from __future__ import annotations

import pandas as pd

from app.signals.events import extract_ema_interaction, extract_swing_pivot


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _series_df(n: int, *, base: float, step: float) -> list[dict]:
    """A steady linear ramp (step<0 = downtrend) — open/high/low/close around it."""
    rows = []
    for i in range(n):
        c = base + step * i
        o = c - step  # previous level → down bars when step<0
        rows.append({"date": f"2026-01-{(i % 28) + 1:02d}", "open": o,
                     "high": max(o, c) + 0.5, "low": min(o, c) - 0.5,
                     "close": c, "volume": 1000})
    return rows


def test_ema_reject_bear_emitted_on_return_to_ema():
    # Downtrend (price below EMA), then a bar rallies up into the EMA band and
    # closes back below on a down bar → bear ema_reject.
    rows = _series_df(30, base=120.0, step=-1.0)  # closes 120 → 91
    # Reject bar: high spikes up toward the (higher) EMA, close finishes below.
    rows.append({"date": "2026-02-01", "open": 91.0, "high": 98.0, "low": 90.5,
                 "close": 90.8, "volume": 5000})
    evs = extract_ema_interaction(_df(rows), fast=3, slow=5, k=0.5)
    bear = [e for e in evs if e.type == "ema_reject" and e.direction == "bear"]
    assert bear, f"expected a bear ema_reject, got {[(e.type, e.direction) for e in evs]}"
    assert bear[-1].payload.get("ma") in {"ema5", "ema3"}
    assert bear[-1].date == "2026-02-01"


def test_ema_reject_needs_enough_bars():
    rows = _series_df(4, base=100.0, step=-1.0)
    assert extract_ema_interaction(_df(rows), fast=3, slow=5) == []


def test_swing_pivot_lower_high_emitted():
    # Two swing highs, the second lower → bear lower-high. width=2.
    highs = [10, 12, 20, 12, 10, 11, 15, 11, 9]
    rows = [{"date": f"2026-03-{i + 1:02d}", "open": h, "high": h, "low": h - 5,
             "close": h - 1, "volume": 1000} for i, h in enumerate(highs)]
    evs = extract_swing_pivot(_df(rows), width=2)
    lh = [e for e in evs if e.type == "swing_pivot" and e.direction == "bear"]
    assert lh, f"expected a bear lower-high, got {[(e.direction, e.payload) for e in evs]}"
    assert lh[0].payload.get("kind") == "lower_high"


def test_swing_pivot_higher_low_emitted():
    # Two swing lows, the second higher → bull higher-low. width=2.
    lows = [20, 18, 10, 18, 20, 19, 14, 19, 21]
    rows = [{"date": f"2026-04-{i + 1:02d}", "open": lo + 1, "high": lo + 5,
             "low": lo, "close": lo + 1, "volume": 1000} for i, lo in enumerate(lows)]
    evs = extract_swing_pivot(_df(rows), width=2)
    hl = [e for e in evs if e.type == "swing_pivot" and e.direction == "bull"]
    assert hl, f"expected a bull higher-low, got {[(e.direction, e.payload) for e in evs]}"
    assert hl[0].payload.get("kind") == "higher_low"
