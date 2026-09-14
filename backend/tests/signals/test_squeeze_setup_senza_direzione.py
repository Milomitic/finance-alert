"""Una compressione che aspetta di riaprirsi non ha una direzione da dichiarare.

FA-061. Il commento sopra `SqueezeExpansion.proximity` diceva, testualmente,
«this setup carries NO tone: ... saying "bull" here would be inventing a
forecast, which is exactly what setups must not do» — e la riga sotto scriveva
`tone="bull" if ctx.trend_sign >= 0 else "bear"`. Un commento che enuncia la
regola giusta sopra il codice che la viola e' la forma piu' costosa registrata
in CLAUDE.md: e' credibile, quindi chi controlla si ferma al commento.

Misurato in produzione il 2026-09-14: `squeeze_expansion` e' l'UNICO detector i
cui setup convertono in un alert di tono diverso — **63 su 230 collegamenti, il
27%** — e i suoi setup dichiaravano `bull` 487 volte contro `bear` 180.

⚠️ E la suite non poteva vederlo: cambiando il tono, **2.456 test sono passati
senza accorgersene**. Nessuno asseriva il tono di un setup.
"""
import pandas as pd

from app.signals.context import build_context
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.events import Event
from app.signals.setups.base import TONE_BEAR, TONE_BULL, TONE_UNDETERMINED


def _barre(direzione: str) -> pd.DataFrame:
    """40 barre che SALGONO o SCENDONO, per muovere `ctx.trend_sign`.

    E' la meta' che conta: il codice vecchio ramificava proprio su quel segno,
    quindi un test che provasse una sola pendenza sarebbe verde anche con il
    difetto dentro.
    """
    passo = 0.5 if direzione == "su" else -0.5
    prezzo = 100.0
    righe = []
    for i in range(40):
        prezzo += passo
        righe.append({
            "date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
            "open": prezzo, "high": prezzo + 1, "low": prezzo - 1,
            "close": prezzo, "volume": 1000,
        })
    return pd.DataFrame(righe)


def _solo_compressione():
    """Una compressione recente e nessuna espansione: e' un setup, non un segnale."""
    return [Event("2026-02-10", "bb_squeeze", None, magnitude=1.4, payload={"period": 20})]


def test_il_setup_non_dichiara_una_direzione_col_trend_in_su():
    df = _barre("su")
    ctx = build_context(df)
    assert ctx.trend_sign >= 0, "la salita deve produrre un trend positivo, o il caso non distingue"
    s = SqueezeExpansion().proximity(_solo_compressione(), df, ctx)
    assert s is not None
    assert s.tone == TONE_UNDETERMINED


def test_il_setup_non_dichiara_una_direzione_col_trend_in_giu():
    """LO STESSO risultato a trend invertito: e' cio' che prova che il ripiego
    sul trend e' sparito, non solo che oggi rende «undetermined»."""
    df = _barre("giu")
    ctx = build_context(df)
    assert ctx.trend_sign <= 0, "la discesa deve produrre un trend negativo"
    s = SqueezeExpansion().proximity(_solo_compressione(), df, ctx)
    assert s is not None
    assert s.tone == TONE_UNDETERMINED
    assert s.tone not in (TONE_BULL, TONE_BEAR)


def test_il_testo_di_attesa_e_il_tono_dicono_la_STESSA_cosa():
    """La riga portava due affermazioni opposte contemporaneamente: `missing`
    diceva gia' «la direzione non e' ancora decisa» mentre `tone` ne sceglieva
    una. Il difetto non era il tono da solo — era la contraddizione."""
    df = _barre("su")
    s = SqueezeExpansion().proximity(_solo_compressione(), df, build_context(df))
    assert s is not None
    assert "direzione" in s.missing.lower()
    assert s.tone == TONE_UNDETERMINED


def test_il_SEGNALE_invece_una_direzione_ce_l_ha():
    """⚠️ Controllo negativo, e senza di lui i test sopra sarebbero soddisfatti
    anche da un detector che ha smesso di conoscere il verso del tutto.

    L'espansione E' l'evento direzionale: quando le bande si riaprono, da che
    parte si sono riaperte e' un fatto osservato, non una previsione.
    """
    df = _barre("su")
    eventi = _solo_compressione() + [
        Event("2026-02-14", "bb_expansion", "bull", magnitude=0.05, payload={"period": 20})
    ]
    m = SqueezeExpansion().detect(eventi, df, build_context(df))
    assert m is not None
    assert m.tone in (TONE_BULL, TONE_BEAR)
