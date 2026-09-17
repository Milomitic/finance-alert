"""Volatility Squeeze Expansion: Bollinger Bands contract inside Keltner
Channels (a squeeze = energy build-up), then expand; the breakout resolves in
the expansion's direction. Source: Bollinger (2001); TTM Squeeze (Carter,
"Mastering the Trade"). Consumes bb_squeeze + bb_expansion events."""
from __future__ import annotations

import pandas as pd

from app.signals.calibration_map import get_calibration
from app.signals.context import SignalContext
from app.signals.detectors.base import (
    SignalMatch,
    concave,
    find_after,
    invalidazione_da_finestra,
    score_v2,
)
from app.signals.events import Event
from app.signals.setups.base import TONE_UNDETERMINED, SetupMatch

_EXPAND_WINDOW_DAYS = 15
# Forza anchors in raw event-magnitude units.
# tightness = Keltner/Bollinger width ratio; >=1.5 = unusually compressed.
_TIGHTNESS_ANCHORS = (0.95, 1.2, 1.5, 2.0)
# expansion_strength = |close-mid|/mid at the band re-open; >=10% = real release.
_EXPANSION_ANCHORS = (0.03, 0.06, 0.10, 0.15)


class SqueezeExpansion:
    name = "squeeze_expansion"
    tone = "bull"
    sources = ['Bollinger (2001); TTM Squeeze (Carter, "Mastering the Trade")']
    min_bars = 25

    def detect(self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext) -> SignalMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        squeezes = [e for e in events if e.type == "bb_squeeze"]
        if not squeezes:
            return None
        sq = squeezes[-1]
        exp = find_after(events, "bb_expansion", after=sq.date, within_days=_EXPAND_WINDOW_DAYS)
        if exp is None:
            return None
        tone = exp.direction or ("bull" if ctx.trend_sign >= 0 else "bear")
        trend_aligned = (ctx.trend_sign > 0 and tone == "bull") or (ctx.trend_sign < 0 and tone == "bear")
        factors = {
            "tightness": concave(sq.magnitude or 1.0, _TIGHTNESS_ANCHORS),
            "expansion_strength": concave(exp.magnitude or 0.0, _EXPANSION_ANCHORS),
            "trend_alignment": 1.0 if trend_aligned else 0.5,
        }
        weights = {"tightness": 0.8, "expansion_strength": 1.0, "trend_alignment": 0.8}
        # Forza: soft-min over the two STRENGTH factors (tightness + expansion),
        # so a mediocre tightness can't be laundered to 90 by a saturated
        # expansion + alignment — the exact "mediocrity laundering" the study found.
        strength = score_v2(factors, weights,
                            strength_keys={"tightness", "expansion_strength"})
        probability = get_calibration().probability(self.name, factors)
        chain = [
            {"date": sq.date, "label": "Compressione (squeeze)",
             "detail": "Bollinger dentro Keltner: volatilita compressa"},
            {"date": exp.date, "label": f"Espansione {tone}",
             "detail": "le bande si riaprono: rilascio nel verso del trend"},
        ]
        # Il segnale dice «l'energia accumulata si e' rilasciata in questo
        # verso». Tornare oltre il lato opposto della compressione dice che non
        # era un rilascio: la finestra e' quella fra compressione ed espansione,
        # non lo storico.
        invalidation = invalidazione_da_finestra(
            ohlcv, sq.date, exp.date, tone,
            "rientro nella compressione: il rilascio non ha tenuto")
        return SignalMatch(name=self.name, tone=tone,
                           strength=strength, probability=probability,
                           signal_date=exp.date, chain=chain,
                           invalidation=invalidation,
                           factors=factors)

    # ── Setup (pre-trigger) ─────────────────────────────────────────────
    # The purest anticipation case in the engine. A squeeze IS a waiting
    # state — Bollinger compressed inside Keltner means energy building with
    # no direction yet — and it can hold for days. The expansion is the
    # trigger, and by the time bands re-open the move is under way.
    #
    # ⚠️ Questo setup NON porta una direzione, e fino al 2026-09-14 il
    # commento lo diceva mentre la riga sotto scriveva
    # `tone="bull" if ctx.trend_sign >= 0 else "bear"`. Un commento che
    # enuncia la regola giusta sopra il codice che la viola e' la forma che
    # CLAUDE.md registra come la piu' costosa: e' credibile, e chi controlla
    # si ferma al commento.
    #
    # Quanto e' costata, misurata in produzione: `squeeze_expansion` e'
    # l'UNICO detector i cui setup convertono in un alert di tono diverso —
    # 63 su 230 collegamenti, il 27% — e i suoi setup dichiaravano `bull` 487
    # volte contro `bear` 180. Cioe' la schermata mostrava una freccia con un
    # colore direzionale su un'attesa che per costruzione non ha verso.
    #
    # Il ripiego sul trend prevalente NON e' un compromesso accettabile:
    # `missing` dice gia' «la direzione non e' ancora decisa», quindi la riga
    # portava due affermazioni opposte contemporaneamente.
    def proximity(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext
    ) -> SetupMatch | None:
        if len(ohlcv) < self.min_bars:
            return None
        squeezes = [e for e in events if e.type == "bb_squeeze"]
        if not squeezes:
            return None
        sq = squeezes[-1]
        # Already expanded → detect() fired (or the window lapsed); not a setup.
        if find_after(events, "bb_expansion", after=sq.date,
                      within_days=_EXPAND_WINDOW_DAYS) is not None:
            return None

        # A squeeze older than the expansion window never resolved into this
        # signal — stop presenting a stale coil as if it were still loaded.
        last_date = str(ohlcv["date"].iloc[-1])[:10]
        age = _days_between(sq.date, last_date)
        if age is not None and age > _EXPAND_WINDOW_DAYS:
            return None

        tightness = concave(sq.magnitude or 1.0, _TIGHTNESS_ANCHORS)
        # Only one gate of two is outstanding, but that gate is the whole
        # event, so proximity stays mid-band: tighter coils sit higher because
        # they are closer to having to resolve.
        prox = round(0.45 + 0.30 * tightness, 3)
        return SetupMatch(
            detector=self.name,
            tone=TONE_UNDETERMINED,
            proximity=prox,
            missing=(
                "le bande devono riaprirsi (espansione): la compressione e' carica "
                "ma la direzione non e' ancora decisa"
            ),
            factors={"tightness": tightness, "gate_squeeze": 1.0},
            annotations={"levels": [], "points": []},
        )


def _days_between(a: str, b: str) -> int | None:
    """Calendar days between two ISO dates; None if either is unparsable."""
    from datetime import date as _date
    try:
        return (_date.fromisoformat(str(b)[:10]) - _date.fromisoformat(str(a)[:10])).days
    except ValueError:
        return None
