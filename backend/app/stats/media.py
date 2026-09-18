"""Intervalli di confidenza attorno a una MEDIA.

`sizing.py` copre le PROPORZIONI (Wilson). Questo copre le medie di variabili
continue — l'attesa in R di un piano di trade, per cui Wilson non e' definito.

⚠️ Stessa convenzione di `sized_interval`, e cambiarla qui renderebbe due
riquadri incoerenti sullo stesso schermo: la stima puntuale usa TUTTE le
righe, perche' e' la migliore ipotesi disponibile; solo la LARGHEZZA e' pagata
sul numero di osservazioni indipendenti. Finestre di 21 sedute che si
sovrappongono non sono estrazioni indipendenti.

Niente scipy: non e' una dipendenza di questo progetto, e la t di Student si
ottiene dalla beta incompleta regolarizzata che `app/stats/beta.py` gia'
fornisce.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from app.stats.beta import betai

#: Limite superiore della ricerca del quantile. Oltre, la t e' talmente nella
#: coda che l'intervallo non e' comunque leggibile.
_T_MAX = 1e4


def t_cdf(t: float, df: int) -> float:
    """Funzione di ripartizione della t di Student.

    Dalla beta incompleta: P(T <= t) = 1 - I_{df/(df+t^2)}(df/2, 1/2)/2 per
    t >= 0, e simmetrica sotto zero.
    """
    if df < 1 or not math.isfinite(t):
        return float("nan")
    coda = betai(df / 2.0, 0.5, df / (df + t * t)) / 2.0
    return 1.0 - coda if t >= 0 else coda


def t_quantile(p: float, df: int) -> float:
    """Il valore t tale che P(T <= t) = p, per bisezione sulla ripartizione.

    ⚠️ Per bisezione e non con un'approssimazione in forma chiusa: quelle
    tabellate perdono precisione proprio ai gradi di liberta' BASSI, che qui
    sono il caso normale — un detector a 21 sedute su tre mesi di magazzino ha
    una manciata di finestre indipendenti, non centinaia.
    """
    if df < 1 or not (0.0 < p < 1.0):
        return float("nan")
    basso, alto = 0.0, _T_MAX
    for _ in range(200):
        meta = (basso + alto) / 2.0
        if t_cdf(meta, df) < p:
            basso = meta
        else:
            alto = meta
    return (basso + alto) / 2.0


def mean_interval(
    valori: Sequence[float], *, effective_n: int, confidenza: float = 0.95,
) -> tuple[float, float] | None:
    """Intervallo attorno alla media di `valori`, largo quanto `effective_n`
    osservazioni indipendenti giustificano.

    None sotto le due osservazioni indipendenti, o su un campione vuoto.

    ⚠️ None e non un intervallo larghissimo: con una sola osservazione
    indipendente la dispersione non e' stimabile, e stampare un intervallo
    comunque suggerirebbe che una misura ci sia. «Non concludente» e' la
    risposta vera, ed e' quella che questo progetto ha gia' scelto di dare
    sedici volte su sedici nel cubo dei detector.
    """
    n = len(valori)
    if n < 2 or effective_n < 2:
        return None
    media = sum(valori) / n
    # Deviazione standard CAMPIONARIA su tutte le righe: la dispersione e' una
    # proprieta' del fenomeno, non del numero di finestre indipendenti.
    varianza = sum((v - media) ** 2 for v in valori) / (n - 1)
    errore = math.sqrt(varianza) / math.sqrt(effective_n)
    meta = t_quantile(1.0 - (1.0 - confidenza) / 2.0, effective_n - 1) * errore
    return (media - meta, media + meta)
