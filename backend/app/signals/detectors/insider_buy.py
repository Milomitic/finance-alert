"""InsiderBuy Confirmation (H3): Insider-cluster buy confirmed by a technical
oversold condition or price near support.

Hypothesis: insider purchases cluster before a price recovery, especially
when the stock is technically oversold or sitting on a key support level.
Source: Lakonishok & Lee (2001) "Are Insider Trades Informative?".

Trigger conditions (bull only):
  - An "insider_cluster" event with direction="bull" in the recent window.
  - At least one technical confirmation within _CONF_WINDOW_DAYS after the
    cluster date:
      * "rsi_extreme" with direction="bull" (oversold), OR
      * "sr_level" with kind="support" whose level is within 3% of last close.

Confidence factors:
  - cluster_magnitude: gate factor -- the insider buy cluster strength.
  - rsi_confirmation: clamp(rsi_magnitude) if an oversold RSI is present.
  - support_proximity: 1 - (gap_pct / 0.03) if price is near a support.
"""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import SignalMatch, clamp01, concave, find_after, score_v2
from app.signals.events import Event

# Calendar days after the insider cluster to look for confirmation.
_CONF_WINDOW_DAYS = 30

# Max distance from support level to last close to count as "near support".
_SUPPORT_PROXIMITY_PCT = 0.03

# Forza anchors. rsi_confirmation is clamp01(rsi_mag) (already 0..1).
# support_proximity is 1 - gap_pct/0.03 — a 0..1 proximity (1 = exactly on the
# level). Both live in 0..1: raw value at curve-contribution 0.45 / 0.75 / 0.88
# + saturating ceil.
_RSI_CONFIRMATION_ANCHORS = (0.20, 0.40, 0.60, 0.80)
_SUPPORT_PROXIMITY_ANCHORS = (0.50, 0.80, 0.95, 0.99)


class InsiderBuy:
    name = "insider_buy"
    tone = "bull"
    sources = [
        "Lakonishok & Lee (2001) insider buying as a bullish signal",
        "insider cluster: multiple distinct purchases in a 30-day window",
    ]
    min_bars = 25

    def detect(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext,
    ) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None

        # Find the most recent bull insider_cluster event.
        cluster_evt: Event | None = None
        for e in reversed(events):
            if e.type == "insider_cluster" and e.direction == "bull":
                cluster_evt = e
                break
        if cluster_evt is None:
            return None

        cluster_mag = cluster_evt.magnitude or 0.0

        # --- Technical confirmation 1: oversold RSI ---
        rsi_conf: Event | None = None
        # Check same date or after.
        for e in events:
            if (e.type == "rsi_extreme" and e.direction == "bull"
                    and e.date >= cluster_evt.date):
                rsi_conf = e
                break
        if rsi_conf is None:
            rsi_conf = find_after(
                events, "rsi_extreme",
                after=cluster_evt.date,
                within_days=_CONF_WINDOW_DAYS,
                direction="bull",
            )

        # --- Technical confirmation 2: price near support ---
        support_evt: Event | None = None
        best_proximity = 0.0
        for e in events:
            if e.type != "sr_level":
                continue
            if e.payload.get("kind") != "support":
                continue
            level = e.payload.get("level")
            if not isinstance(level, (int, float)):
                continue
            if ctx.last_close <= 0:
                continue
            gap_pct = abs(ctx.last_close - level) / ctx.last_close
            if gap_pct <= _SUPPORT_PROXIMITY_PCT:
                proximity = 1.0 - gap_pct / _SUPPORT_PROXIMITY_PCT
                if proximity > best_proximity:
                    best_proximity = proximity
                    support_evt = e

        # Require at least one confirmation.
        if rsi_conf is None and support_evt is None:
            return None

        # Build factors.
        rsi_mag = (rsi_conf.magnitude or 0.0) if rsi_conf else 0.0
        factors: dict[str, float] = {
            # Gate factor: insider cluster magnitude (not in weighted score).
            "cluster_magnitude": clamp01(cluster_mag),
            "rsi_confirmation": concave(clamp01(rsi_mag), _RSI_CONFIRMATION_ANCHORS),
            "support_proximity": concave(clamp01(best_proximity), _SUPPORT_PROXIMITY_ANCHORS),
        }
        weights = {"rsi_confirmation": 1.0, "support_proximity": 0.8}
        # Forza: soft-min over the genuine STRENGTH factors (rsi_confirmation +
        # support_proximity); cluster_magnitude is a gate prerequisite, excluded
        # from both the weights and the cap.
        strength = score_v2(
            factors, weights,
            strength_keys={"rsi_confirmation", "support_proximity"},
        )
        # Probabilità: empirical hit-rate "di accadimento" for this detector.
        probability = get_calibration().probability(self.name, factors)

        # Use the confirmation date as signal_date (more recent = more current).
        if rsi_conf is not None and support_evt is not None:
            signal_date = max(rsi_conf.date, support_evt.date)
        elif rsi_conf is not None:
            signal_date = rsi_conf.date
        else:
            assert support_evt is not None
            signal_date = support_evt.date

        # Build the chain.
        n_buyers = cluster_evt.payload.get("n_buyers", "?")
        total_shares = cluster_evt.payload.get("total_shares")
        shares_txt = f"{int(total_shares):,}" if isinstance(total_shares, (int, float)) else "n/d"
        chain: list[dict] = [
            {
                "date": cluster_evt.date,
                "label": f"Insider buying cluster ({n_buyers} insiders, {shares_txt} shares)",
                "detail": (
                    f"Cluster di acquisti da {n_buyers} insider distinti "
                    f"({shares_txt} azioni totali). "
                    "Segnale storicamente bullish (Lakonishok & Lee 2001)."
                ),
                "source": "insider",
            },
        ]

        if rsi_conf is not None:
            rsi_val = rsi_conf.payload.get("rsi")
            rsi_txt = f"{rsi_val:.1f}" if isinstance(rsi_val, (int, float)) else "n/d"
            chain.append({
                "date": rsi_conf.date,
                "label": f"RSI oversold ({rsi_txt}) - conferma tecnica",
                "detail": (
                    f"RSI={rsi_txt}: titolo ipervenduto al momento degli acquisti "
                    "insider. Combinazione storicamente favorevole."
                ),
            })

        if support_evt is not None:
            s_level = support_evt.payload.get("level")
            s_txt = f"{s_level:.2f}" if isinstance(s_level, (int, float)) else "n/d"
            chain.append({
                "date": support_evt.date,
                "label": f"Supporto tecnico a {s_txt} - conferma strutturale",
                "detail": (
                    f"Prezzo vicino al supporto {s_txt} "
                    f"(dist. {best_proximity * _SUPPORT_PROXIMITY_PCT * 100:.2f}%). "
                    "Gli insider comprano mentre il titolo e' vicino a un livello chiave."
                ),
            })

        invalidation = {
            "level": float(ctx.last_close * 0.95),
            "reason": "Chiusura sotto il 5% dal close annulla il setup insider",
        }

        return SignalMatch(
            name=self.name,
            tone=self.tone,
            strength=strength,
            probability=probability,
            signal_date=signal_date,
            chain=chain,
            invalidation=invalidation,
            factors=factors,
        )
