"""PEAD - Post-Earnings-Announcement Drift (H1): earnings surprise confirmed
by a gap and/or volume spike on or near the earnings date.

Hypothesis: a meaningful EPS beat (or miss) accompanied by an opening gap and
elevated volume is more likely to drift in the surprise direction over the
following weeks than to reverse immediately. Based on the academic finding by
Bernard and Thomas (1989) that the market systematically underreacts to earnings
surprises, with price drift persisting for ~60 days post-announcement.

Trigger conditions (bull example):
  - An "earnings_surprise" event with direction="bull" (EPS beat)
  - At least one of:
      * a "gap" event with direction="bull" on or within CONF_WINDOW_DAYS
        after the earnings date
      * a "volume_spike" event on or within CONF_WINDOW_DAYS after the
        earnings date (direction-neutral: big volume = participation)

Confidence factors:
  - surprise_strength: magnitude of the earnings surprise (gate, not weighted)
  - gap_size: magnitude of the confirming gap (weighted)
  - volume_strength: relative volume strength (weighted)
"""
from __future__ import annotations

import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, find_after, score
from app.signals.events import Event

# Maximum calendar days after the earnings date to look for confirmation.
_CONF_WINDOW_DAYS = 3


def _closes_in_direction(ohlcv: pd.DataFrame, iso_date: str, tone: str) -> bool:
    """True if the bar at `iso_date` closes in the surprise direction (a green
    candle for bull, red for bear). Validates the volume confirmation: a
    high-volume day that closed AGAINST the surprise - e.g. a gap-up sold off
    into a red candle - is distribution, not follow-through, and must not
    confirm the drift. Real case: NIO 2026-05-21 spiked 3.2x volume but closed
    a deep red candle (open 5.92 -> close 5.60); without this gate the volume
    alone fired a bull PEAD right before the stock fell."""
    try:
        d = ohlcv["date"].astype(str).str[:10]
        rows = ohlcv[d == iso_date[:10]]
        if rows.empty:
            return False
        o = float(rows.iloc[-1]["open"])
        c = float(rows.iloc[-1]["close"])
    except Exception:  # noqa: BLE001 - defensive: never break the scan
        return False
    return c >= o if tone == "bull" else c <= o


class Pead:
    name = "pead"
    tone = "dynamic"  # resolved per-match from the surprise direction
    sources = ["Bernard & Thomas (1989) post-earnings-announcement drift"]
    min_bars = 25

    def detect(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext,
    ) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None

        # Find the most recent earnings_surprise event with a clear direction.
        surprise = None
        for e in reversed(events):
            if e.type == "earnings_surprise" and e.direction in ("bull", "bear"):
                surprise = e
                break
        if surprise is None:
            return None

        tone = surprise.direction  # "bull" or "bear"

        # Find confirmation: gap in the same direction and/or any volume spike,
        # on the same day as the earnings event or within the confirmation window.
        def _same_or_after(e: Event, ref_date: str) -> bool:
            return e.date >= ref_date

        gap_same = next(
            (e for e in events
             if e.type == "gap" and e.direction == tone and e.date == surprise.date),
            None,
        )
        gap_after = find_after(
            events, "gap", after=surprise.date,
            within_days=_CONF_WINDOW_DAYS, direction=tone,
        )
        gap = gap_same or gap_after

        vol_same = next(
            (e for e in events
             if e.type == "volume_spike" and e.date == surprise.date),
            None,
        )
        vol_after = find_after(
            events, "volume_spike", after=surprise.date, within_days=_CONF_WINDOW_DAYS,
        )
        vol = vol_same or vol_after
        # Volume is direction-neutral, so a spike only confirms the drift if
        # ITS bar closed in the surprise direction. The gap path is already
        # directional (extract_gap only emits a held gap), so it needs no
        # extra check here.
        if vol is not None and not _closes_in_direction(ohlcv, vol.date, tone):
            vol = None

        # Require at least one confirming event.
        if gap is None and vol is None:
            return None

        gap_mag = (gap.magnitude or 0.0) if gap else 0.0
        vol_mag = (vol.magnitude or 1.0) if vol else 1.0
        surprise_mag = surprise.magnitude or 0.0

        factors = {
            # Gate factor (not in weights): surprise strength validates the premise.
            # Kept in factors dict for transparency / frontend display.
            "surprise_strength": clamp01(surprise_mag),
            "gap_size": clamp01(gap_mag / 0.04),       # 4% gap = full
            "volume_strength": clamp01((vol_mag - 1.0) / 2.0),  # 3x avg = full
        }
        conf = score(
            factors,
            {"gap_size": 1.0, "volume_strength": 0.8},  # surprise is gate, not weighted
        )

        sp = surprise.payload.get("surprise_pct")
        sp_txt = f"{sp:+.1f}%" if isinstance(sp, (int, float)) else "n/d"
        conf_date = gap.date if gap else (vol.date if vol else surprise.date)
        signal_date = conf_date

        chain: list[dict] = [
            {
                "date": surprise.date,
                "label": f"Earnings drift {'beat' if tone == 'bull' else 'miss'} ({sp_txt})",
                "detail": f"sorpresa EPS {sp_txt}: drift post-earnings atteso",
                "source": "earnings",
            },
        ]
        if gap:
            gp = gap.payload.get("gap_pct")
            gp_txt = f"{gp * 100:.1f}%" if isinstance(gp, (int, float)) else "n/d"
            chain.append({
                "date": gap.date,
                "label": f"Gap {tone} di conferma",
                "detail": f"apertura in gap del {gp_txt} dopo gli utili",
            })
        if vol:
            chain.append({
                "date": vol.date,
                "label": "Volume spike di conferma",
                "detail": f"{vol_mag:.1f}x la media: reazione partecipata",
            })

        inv_direction = "ribasso" if tone == "bull" else "rialzo"
        invalidation = {
            "level": float(ctx.last_close * (0.97 if tone == "bull" else 1.03)),
            "reason": f"Chiusura in {inv_direction} del 3% annulla il drift",
        }

        return SignalMatch(
            name=self.name,
            tone=tone,
            confidence=conf,
            signal_date=signal_date,
            chain=chain,
            invalidation=invalidation,
            factors=factors,
        )
