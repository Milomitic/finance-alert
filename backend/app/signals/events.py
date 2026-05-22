"""Dated technical events extracted from an OHLCV window.

An Event is a fact that happened ON a specific bar. Detectors consume
streams of these to recognise multi-step setups over time. Extractors scan
the recent window and may emit several events (one per qualifying bar)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Event:
    date: str                       # ISO YYYY-MM-DD — the bar it occurs on
    type: str                       # "breakout" | "volume_spike" | ...
    direction: str | None = None    # "bull" | "bear" | None
    magnitude: float | None = None  # normalised strength (ratio, % amplitude)
    payload: dict[str, Any] = field(default_factory=dict)


def _iso(v: Any) -> str:
    s = str(v)
    return s[:10]


def extract_breakout(ohlcv: pd.DataFrame, *, lookback: int = 20) -> list[Event]:
    """Emit a bull event when a bar's close exceeds the prior `lookback`-bar
    high (Donchian breakout), a bear event when it breaks the prior low.
    Compares against the window BEFORE each bar (shifted) to avoid look-ahead."""
    if len(ohlcv) < lookback + 1:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    high = ohlcv["high"].astype(float).reset_index(drop=True)
    low = ohlcv["low"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    prior_high = high.shift(1).rolling(lookback).max()
    prior_low = low.shift(1).rolling(lookback).min()
    out: list[Event] = []
    for i in range(lookback, len(close)):
        ph, pl = prior_high.iloc[i], prior_low.iloc[i]
        if pd.notna(ph) and close.iloc[i] > ph:
            out.append(Event(_iso(dates.iloc[i]), "breakout", "bull",
                             magnitude=float((close.iloc[i] - ph) / ph) if ph else None,
                             payload={"level": float(ph), "lookback": lookback}))
        elif pd.notna(pl) and close.iloc[i] < pl:
            out.append(Event(_iso(dates.iloc[i]), "breakout", "bear",
                             magnitude=float((pl - close.iloc[i]) / pl) if pl else None,
                             payload={"level": float(pl), "lookback": lookback}))
    return out


def extract_volume_spike(
    ohlcv: pd.DataFrame, *, avg_period: int = 20, k: float = 2.0,
) -> list[Event]:
    """Emit an event on each bar whose volume >= k x its trailing avg."""
    if len(ohlcv) < avg_period + 1:
        return []
    vol = ohlcv["volume"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    avg = vol.shift(1).rolling(avg_period).mean()
    out: list[Event] = []
    for i in range(avg_period, len(vol)):
        a = avg.iloc[i]
        if pd.notna(a) and a > 0 and vol.iloc[i] >= k * a:
            out.append(Event(_iso(dates.iloc[i]), "volume_spike", None,
                             magnitude=float(vol.iloc[i] / a),
                             payload={"avg_period": avg_period}))
    return out


# Registry of active extractors for Phase 1a. Each is f(ohlcv) -> list[Event].
EXTRACTORS = [
    lambda df: extract_breakout(df, lookback=20),
    lambda df: extract_volume_spike(df, avg_period=20, k=2.0),
]


def extract_events(ohlcv: pd.DataFrame) -> list[Event]:
    """Run all extractors; return events sorted by date ascending."""
    events: list[Event] = []
    for fn in EXTRACTORS:
        try:
            events.extend(fn(ohlcv))
        except Exception:  # noqa: BLE001 — one bad extractor must not kill the rest
            continue
    return sorted(events, key=lambda e: e.date)
