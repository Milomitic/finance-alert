"""Gli indicatori del grafico in forma compatta (FA-182).

Nella forma estesa ogni punto e' `{"date": "2016-05-05", "value": 3.66}`: dieci
serie per ~2.650 barre fanno 1,1 MB dei 1,27 del dettaglio di un titolo, quasi
tutti date ripetute dieci volte e cifre oltre la quindicesima. Nella forma
compatta una serie e' l'elenco dei soli valori, uno per barra di `ohlcv` (o di
`bars` per un mercato) e nello stesso ordine; vuota se l'indicatore non c'e'.

E' a richiesta (`?formato=compatto`): una scheda aperta prima del rilascio ha
in memoria il codice che legge la forma estesa, e la riceve ancora.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Literal

#: Le serie del grafico, con le chiavi della risposta.
SERIE = (
    "ema20", "ema50", "ema200", "rsi14", "bb_upper", "bb_middle", "bb_lower",
    "macd_line", "macd_signal", "macd_hist",
)

Formato = Literal["esteso", "compatto"]

#: Sette cifre significative: 26658.25 resta 26658.25 e un MACD di 0,000123456
#: resta 0,0001234560. Il grafico ne mostra al piu' quattro.
_CIFRE = 7


def arrotonda(v: float | None) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return float(f"{f:.{_CIFRE}g}")


def compatta(punti: Sequence[Any], date_barre: Sequence[Any]) -> list[float | None]:
    """I valori di `punti` (oggetti con `.date` e `.value`) allineati a
    `date_barre`. Se la serie e' gia' allineata — il caso di oggi, un punto
    per barra — si legge per posizione; altrimenti per data, con None dove
    manca, cosi' un disallineamento futuro non sposta i valori di una barra."""
    if not punti:
        return []
    if len(punti) == len(date_barre) and all(
        p.date == d for p, d in zip(punti, date_barre, strict=True)
    ):
        return [arrotonda(p.value) for p in punti]
    per_data = {p.date: p.value for p in punti}
    return [arrotonda(per_data.get(d)) for d in date_barre]


def serie_compatte(fonte: Any, date_barre: Sequence[Any]) -> dict[str, list[float | None]]:
    """Le dieci serie di `fonte` (attributi con i nomi di `SERIE`)."""
    return {k: compatta(getattr(fonte, k, None) or [], date_barre) for k in SERIE}
