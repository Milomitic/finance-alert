"""Phase 1 — chain enrichment: append co-temporal, same-tone confirmation
events (already in the stream) to a primary SignalMatch's Catena, and stamp a
bounded `confirmation_count` factor. Display + evidence only: Forza/Probabilità
are NOT recomputed here (the factor is plumbed for Phase 3 calibration)."""
from __future__ import annotations

import pandas as pd

from app.signals.chain_enrichment import enrich_chain
from app.signals.detectors.base import SignalMatch
from app.signals.events import Event
from app.signals.horizon import classify_horizon


def _ohlcv(n: int = 12, *, last: str = "2026-05-26") -> pd.DataFrame:
    """n daily bars ending at `last`. Down-bars (close<open) by default so a
    volume_spike on a recent bar reads as bear."""
    dates = pd.bdate_range(end=last, periods=n)
    rows = []
    px = 700.0
    for d in dates:
        o = px
        c = px - 2.0  # down-bar
        rows.append({"date": d.strftime("%Y-%m-%d"), "open": o, "high": o + 1,
                     "low": c - 1, "close": c, "volume": 1_000_000})
        px = c
    return pd.DataFrame(rows)


def _match(tone: str = "bear", *, signal_date: str = "2026-05-26") -> SignalMatch:
    chain = [
        {"date": "2026-03-01", "label": f"Incrocio EMA {tone}", "detail": "death cross"},
        {"date": signal_date, "label": "Pullback + ripresa", "detail": "ritorno verso EMA"},
    ]
    return SignalMatch(name="trend_pullback", tone=tone, signal_date=signal_date,
                       chain=chain, invalidation={"level": 651.0, "reason": "x"},
                       factors={"trend_strength": 0.6}, strength=65, probability=58)


def test_appends_cotemporal_same_tone_confirmation():
    df = _ohlcv()
    events = [Event("2026-05-26", "macd_cross", "bear", magnitude=1.0)]
    out = enrich_chain(_match(), events, df)
    # chain grew by exactly one confirmation step, tagged kind=confirmation.
    assert len(out.chain) == 3
    conf = [s for s in out.chain if s.get("kind") == "confirmation"]
    assert len(conf) == 1
    assert "MACD" in conf[0]["label"]
    # bounded factor present (1 of >=3 -> 1/3).
    assert out.factors["confirmation_count"] == 1 / 3


def test_skips_wrong_tone_confirmation():
    df = _ohlcv()
    events = [Event("2026-05-26", "macd_cross", "bull", magnitude=1.0)]  # bull vs bear match
    out = enrich_chain(_match(tone="bear"), events, df)
    assert len(out.chain) == 2  # nothing appended
    assert "confirmation_count" not in out.factors


def test_skips_out_of_window_confirmation():
    df = _ohlcv(n=40, last="2026-05-26")
    # An old bear confirmation ~30 bars before the signal date.
    events = [Event(df["date"].iloc[2], "rsi_divergence", "bear", magnitude=0.5)]
    out = enrich_chain(_match(), events, df, window_bars=5)
    assert len(out.chain) == 2


def test_volume_spike_tone_derived_from_bar_direction():
    df = _ohlcv()  # down-bars -> bear
    events = [Event("2026-05-26", "volume_spike", None, magnitude=3.0)]
    out = enrich_chain(_match(tone="bear"), events, df)
    conf = [s for s in out.chain if s.get("kind") == "confirmation"]
    assert len(conf) == 1
    assert "Volume" in conf[0]["label"]


def test_confirmation_count_bounded_at_one():
    df = _ohlcv()
    d = "2026-05-26"
    events = [
        Event(d, "macd_cross", "bear", magnitude=1.0),
        Event(d, "candle_reversal", "bear", magnitude=0.8, payload={"pattern": "shooting_star"}),
        Event(d, "rsi_extreme", "bear", magnitude=0.7),
        Event(d, "rsi_divergence", "bear", magnitude=0.6),
    ]
    out = enrich_chain(_match(), events, df)
    assert out.factors["confirmation_count"] == 1.0  # min(4,3)/3


def test_dedup_one_step_per_type_keeps_closest_to_signal():
    df = _ohlcv()
    last = df["date"].iloc[-1]
    earlier = df["date"].iloc[-4]
    events = [
        Event(earlier, "macd_cross", "bear", magnitude=1.0),
        Event(last, "macd_cross", "bear", magnitude=1.0),  # whipsaw, same type
    ]
    out = enrich_chain(_match(signal_date=last), events, df)
    conf = [s for s in out.chain if s.get("kind") == "confirmation"]
    assert len(conf) == 1  # collapsed to one MACD step
    assert conf[0]["date"] == last  # the one closest to the signal bar
    assert out.factors["confirmation_count"] == 1 / 3


def test_no_confirmations_leaves_match_unchanged():
    df = _ohlcv()
    out = enrich_chain(_match(), [], df)
    assert len(out.chain) == 2
    assert "confirmation_count" not in out.factors


def test_horizon_ignores_confirmation_steps():
    # A long trend_pullback (cross months before the signal) must STAY long even
    # though a confirmation step lands on the signal date.
    chain = [
        {"date": "2026-01-05", "label": "Incrocio EMA bear", "detail": "death cross"},
        {"date": "2026-05-26", "label": "Pullback + ripresa", "detail": "x"},
        {"date": "2026-05-26", "label": "MACD cross ribassista", "detail": "y", "kind": "confirmation"},
    ]
    assert classify_horizon("trend_pullback", chain) == "long"
