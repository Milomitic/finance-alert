"""Phase 1 — co-temporal chain enrichment.

A continuation SignalMatch (today: trend_pullback) fires off ONE event and
hand-builds a 2-step Catena, ignoring every other confirmation already present
in the same `events` list. This pass scans that list for same-tone events dated
within a tight window of the signal bar and appends them as numbered Catena
steps tagged ``kind="confirmation"`` — so the chain literally grows with the
reinforcing price action the user reads on the chart (EMA reject, RSI rollover,
volume on the move, MACD cross, …).

DISPLAY + EVIDENCE ONLY. Forza/Probabilità are NOT recomputed here. We stamp a
bounded ``confirmation_count`` factor (0..1) for a future, calibrated scoring
pass (spec Phase 3); in Phase 1 no detector weights reference it, so the score
is unchanged. The confirmation steps are excluded from horizon-span computation
(see ``classify_horizon``) so enrichment can't shift the timeframe label.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from app.signals.detectors.base import SignalMatch
from app.signals.events import Event

# Detectors whose chains we enrich. The reinforcement concept is GENERAL — any
# technical continuation/reversal setup benefits from showing its co-temporal
# confirmations — so this covers the whole technical family, not just the
# pullback that motivated it. (Pure-fundamental detectors — pead /
# analyst_momentum / insider_buy — are excluded: their chains are hybrid with
# source badges and a different confirmation semantics; a separate pass can
# enrich those later.)
ENRICHABLE = {
    "trend_pullback", "volume_breakout", "high52_momentum", "squeeze_expansion",
    "gap_and_go", "adx_confirmation", "sr_flip", "structure_break",
    "rsi_divergence", "macd_divergence", "hidden_divergence",
    "oversold_reversal", "candle_reversal", "chart_pattern",
}

# Per-detector trigger event types to EXCLUDE from its own confirmations, so a
# detector never re-counts the very event it fired on (chain-level
# de-correlation). Only types that also appear in _CONFIRMATION_TYPES actually
# matter; the rest are documented for clarity. trend_pullback fires on
# `ema_cross`, NOT `ema_reject` — so an EMA reject legitimately reinforces it.
_OWN_EVENT_TYPES: dict[str, set[str]] = {
    "trend_pullback": {"ema_cross"},
    "volume_breakout": {"breakout", "volume_spike"},
    "gap_and_go": {"gap", "volume_spike"},
    "adx_confirmation": {"adx_trend", "breakout"},
    "oversold_reversal": {"rsi_extreme", "sr_level"},
    "candle_reversal": {"candle_reversal", "sr_level"},
    "rsi_divergence": {"rsi_divergence"},
    "hidden_divergence": {"hidden_divergence"},
    "macd_divergence": {"macd_divergence"},
    "squeeze_expansion": {"bb_squeeze", "bb_expansion"},
    "structure_break": {"swing_pivot"},
    "chart_pattern": {"swing_pivot"},
    "sr_flip": {"sr_level"},
}

# Direction-tagged confirmation event types we recognise as reinforcing a
# continuation thesis. volume_spike carries no direction → tone is derived from
# the bar's body (handled below). ema_reject / swing_pivot land in Phase 2 but
# are recognised here so wiring them later needs no change to this module.
_CONFIRMATION_TYPES = {
    "macd_cross",
    "candle_reversal",
    "rsi_extreme",
    "rsi_divergence",
    "volume_spike",
    "adx_trend",
    "ema_reject",
    "swing_pivot",
}


def _conf_label(ev: Event, tone: str) -> tuple[str, str] | None:
    """Italian (label, detail) for a confirmation event, or None to skip."""
    t = ev.type
    if t == "macd_cross":
        return ("MACD cross " + ("rialzista" if tone == "bull" else "ribassista"),
                "incrocio MACD nel verso del segnale")
    if t == "candle_reversal":
        pat = (ev.payload or {}).get("pattern", "")
        return ("Candela di rifiuto", f"pattern {pat}".strip() or "candela di rifiuto al livello")
    if t == "rsi_extreme":
        return ("RSI " + ("ipervenduto" if tone == "bull" else "ipercomprato"),
                "estremo RSI a conferma del segnale")
    if t == "rsi_divergence":
        return ("Divergenza RSI " + ("rialzista" if tone == "bull" else "ribassista"),
                "divergenza prezzo / RSI")
    if t == "volume_spike":
        return ("Volume sulla " + ("salita" if tone == "bull" else "discesa"),
                "volume sopra la media nel verso del segnale")
    if t == "adx_trend":
        return ("Trend ADX in rafforzamento", "ADX conferma la forza del trend")
    if t == "ema_reject":  # Phase 2 primitive
        ma = str((ev.payload or {}).get("ma", "EMA")).upper()
        return (f"Rifiuto su {ma}", "ritorno alla media e rifiuto nel verso del trend")
    if t == "swing_pivot":  # Phase 2 primitive
        return (("Lower-high confermato" if tone == "bear" else "Higher-low confermato"),
                "struttura a conferma della continuazione")
    return None


def _bar_tone(ohlcv: pd.DataFrame, idx: int) -> str | None:
    """Bull/bear from the bar body (for direction-less events like volume)."""
    try:
        row = ohlcv.iloc[idx]
        c, o = float(row["close"]), float(row["open"])
    except (KeyError, IndexError, ValueError, TypeError):
        return None
    if c > o:
        return "bull"
    if c < o:
        return "bear"
    return None


def enrich_chain(
    match: SignalMatch | None,
    events: list[Event],
    ohlcv: pd.DataFrame,
    *,
    window_bars: int = 5,
    max_appends: int = 5,
) -> SignalMatch | None:
    """Return `match` with co-temporal same-tone confirmations appended to its
    chain and a bounded `confirmation_count` factor. Pure: builds a new
    SignalMatch (frozen dataclass) and never mutates the input.

    Only enriches matches whose detector is in ENRICHABLE. A no-op (returns the
    same match unchanged) when there are no qualifying confirmations.
    """
    if match is None or not events or match.name not in ENRICHABLE:
        return match
    if ohlcv is None or "date" not in ohlcv:
        return match

    bar_dates = [str(d)[:10] for d in ohlcv["date"].tolist()]
    idx_of = {d: i for i, d in enumerate(bar_dates)}
    anchor = idx_of.get(str(match.signal_date)[:10], len(bar_dates) - 1)

    existing = {(str(s.get("date"))[:10], s.get("label")) for s in match.chain}
    # At most ONE confirmation per event TYPE: a whipsaw that prints two MACD
    # crosses in three bars is one confirmation, not two. Keep the occurrence
    # CLOSEST to the signal bar (largest bar index ≤ anchor window). This also
    # makes confirmation_count count distinct KINDS, not repeats — the honest
    # measure and the one Phase-3 de-correlation wants.
    best: dict[str, tuple[int, dict]] = {}  # type -> (bar_index, step)
    own = _OWN_EVENT_TYPES.get(match.name, set())  # the detector's own trigger(s)

    for ev in events:
        if ev.type not in _CONFIRMATION_TYPES or ev.type in own:
            continue
        day = str(ev.date)[:10]
        ei = idx_of.get(day)
        if ei is None or abs(ei - anchor) > window_bars:
            continue
        # Tone match: direction-tagged events by direction; volume by bar body.
        if ev.type == "volume_spike":
            if _bar_tone(ohlcv, ei) != match.tone:
                continue
        elif ev.direction != match.tone:
            continue

        labels = _conf_label(ev, match.tone)
        if labels is None:
            continue
        label, detail = labels
        if (day, label) in existing:
            continue
        prev = best.get(ev.type)
        if prev is None or ei > prev[0]:
            best[ev.type] = (ei, {"date": day, "label": label,
                                  "detail": detail, "kind": "confirmation"})

    if not best:
        return match

    appended = [step for _, step in best.values()]
    appended.sort(key=lambda s: s["date"])
    appended = appended[:max_appends]
    # ONE chronological chain (oldest → newest): merge cause + confirmation
    # steps and stable-sort by date, so the numbered Catena AND the chart
    # markers read in time order. Stable sort keeps same-date cause steps before
    # same-date confirmations (cause steps come first in the merged list).
    new_chain = sorted([*match.chain, *appended], key=lambda s: str(s.get("date") or "")[:10])
    new_factors = dict(match.factors)
    # Bounded: saturates at 3 distinct confirmation kinds so a wall of correlated
    # events can't run away. Stays OUT of every detector's strength_keys (Phase 3
    # calibrates it into Probabilità; Phase 1 leaves the score untouched).
    new_factors["confirmation_count"] = min(len(appended), 3) / 3.0
    return replace(match, chain=new_chain, factors=new_factors)
